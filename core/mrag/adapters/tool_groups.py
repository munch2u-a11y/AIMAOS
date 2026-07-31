"""Two-layer tool schemas and sequential subagent tool execution.

A small-context main agent can't afford full tool schemas in its window.
This module splits tool knowledge across two layers:

- **Layer A (main agent)**: one line per tool *group* — name, tool count,
  one-sentence summary. A dozen groups cost tens of tokens, not thousands.
- **Layer B (subagent)**: the full per-tool schemas, parameter breakdowns,
  and usage notes for ONE group, given only to a throwaway subagent that
  runs in its own fresh context window.

Flow: the main agent requests a group with a natural-language task; the
runner spins up a subagent (same local model, separate context) that sees
that group's full manifest, executes tools step by step, and writes a
final report. The report is clamped to a token cap and handed back for
appending into the main agent's rolling window — the main agent then
resumes its prior context with just that report added.

Resource discipline: everything is sequential — one LLM call in flight at
any moment (the main agent is paused while its subagent works), so a
consumer CPU/GPU never runs two generations at once. Latency is accepted;
contention is not.

Memory discipline: tool observations that carry *new information* (not
bare confirmations) are ingested verbatim into Layer 1 memory with
source="tool_return", exactly like conversational input — so facts a tool
brought in are retrievable later even after they leave every context
window. Oversized observations are truncated in the subagent's transcript
but stored whole in memory.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from mrag.core.memory_ingestor import MemoryIngestor, chunk_text, SOURCE_TOOL_RETURN
from mrag.core.token_counting import count_text_tokens

logger = logging.getLogger("mrag.adapters.tool_groups")

# An observation at or under this many tokens is treated as a bare
# confirmation ("ok", "saved", "3 rows updated") and not ingested into
# memory; anything longer is new information worth keeping. Tools can
# override per-tool via Tool.informational.
CONFIRMATION_TOKEN_THRESHOLD = 25

# Observation slice shown to the subagent when a tool return is large;
# the full return still goes to memory verbatim.
DEFAULT_OBSERVATION_TOKENS = 600

DEFAULT_MAX_STEPS = 10
DEFAULT_REPORT_MAX_TOKENS = 800

# Marker prefix a runner puts on reports that ended before the task was
# finished (step budget exhausted). The orchestrator's extension policy
# keys off this string — see ToolOrchestrator.
INCOMPLETE_MARKER = "INCOMPLETE"


@dataclass
class Tool:
    """One callable tool. `parameters` is a plain dict describing args
    (JSON-schema style or free-form — it's rendered as documentation for
    the subagent, not validated). `informational`: True = always ingest
    returns into memory, False = never, None = auto by length."""

    name: str
    description: str
    handler: Callable[..., Any]
    parameters: Dict[str, Any] = field(default_factory=dict)
    usage_notes: str = ""
    informational: Optional[bool] = None


@dataclass
class ToolGroup:
    name: str
    summary: str
    tools: List[Tool] = field(default_factory=list)

    def get_tool(self, name: str) -> Optional[Tool]:
        for tool in self.tools:
            if tool.name == name:
                return tool
        return None


class CompositeToolGroup:
    """A group too large for one subagent, divided into subgroups behind a
    sub-orchestrator.

    Subagents work best with 1-5 tools; a suite like a full email
    interface exceeds that. A composite group registers like any other
    group — the top-level planner sees one line — but when a task routes
    to it, a nested orchestrator plans within its own subgroup registry
    and runs one subagent per subtask, recursively following the same
    sequential, scratchpad, tail-summary flow."""

    def __init__(self, name: str, summary: str, registry: "ToolGroupRegistry"):
        self.name = name
        self.summary = summary
        self.registry = registry

    @property
    def tools(self) -> List[Tool]:
        return [
            tool
            for group_name in self.registry.group_names()
            for tool in self.registry.get(group_name).tools
        ]

    def get_tool(self, name: str) -> Optional[Tool]:
        for tool in self.tools:
            if tool.name == name:
                return tool
        return None


class ToolGroupRegistry:
    """Holds the groups and renders both schema layers."""

    def __init__(self):
        self._groups: Dict[str, ToolGroup] = {}

    def register(self, group: ToolGroup):
        self._groups[group.name] = group

    def get(self, name: str) -> Optional[ToolGroup]:
        return self._groups.get(name)

    def group_names(self) -> List[str]:
        return list(self._groups)

    def main_agent_brief(self) -> str:
        """Layer A: the slim block the main agent keeps in its window."""
        if not self._groups:
            return ""
        lines = [
            "Available tool groups — to use one, respond with exactly:",
            '{"tool_group": "<name>", "task": "<what you need done, with all specifics>"}',
        ]
        for group in self._groups.values():
            if isinstance(group, CompositeToolGroup):
                subgroups = len(group.registry.group_names())
                lines.append(
                    f"• {group.name} ({len(group.tools)} tools across "
                    f"{subgroups} subgroups): {group.summary}")
            else:
                lines.append(f"• {group.name} ({len(group.tools)} tools): {group.summary}")
        return "\n".join(lines)

    def subagent_manifest(self, group_name: str,
                          learned: Optional[Dict[str, List[str]]] = None) -> str:
        """Layer B: the full schema breakdown one subagent sees.

        `learned` maps tool name -> promoted knowledge statements (see
        ToolKnowledgeConsolidator.promoted_statements); each tool's
        statements are appended to its own schema entry, so knowledge
        earned by earlier runs becomes part of the tool's description."""
        group = self._groups.get(group_name)
        if not group:
            return ""
        lines = [f"TOOL GROUP '{group.name}': {group.summary}", ""]
        for tool in group.tools:
            lines.append(f"### {tool.name}")
            lines.append(tool.description)
            if tool.parameters:
                lines.append(f"Arguments: {json.dumps(tool.parameters)}")
            if tool.usage_notes:
                lines.append(f"Notes: {tool.usage_notes}")
            statements = (learned or {}).get(tool.name) or []
            if statements:
                lines.append("Learned from prior runs:")
                for statement in statements:
                    lines.append(f"- {statement}")
            lines.append("")
        return "\n".join(lines).strip()


# Matches the first {...} block in model output, tolerating code fences
# and prose around it. Small local models rarely emit clean bare JSON.
_JSON_BLOCK_RE = re.compile(r'\{.*\}', re.DOTALL)


def parse_json_action(text: str) -> Optional[Dict[str, Any]]:
    """Best-effort extraction of one JSON object from model output."""
    m = _JSON_BLOCK_RE.search(text or "")
    if not m:
        return None
    candidate = m.group(0)
    # Trim trailing garbage by shrinking to the last balanced brace.
    depth = 0
    for i, ch in enumerate(candidate):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                candidate = candidate[: i + 1]
                break
    try:
        parsed = json.loads(candidate)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None


class SubAgentToolRunner:
    """Runs one tool-group task in a throwaway subagent context.

    The subagent is the same local model as the main agent, but every
    run starts from a fresh prompt containing only the group manifest
    and the task — the main agent's window is untouched until the final
    report comes back.
    """

    def __init__(
        self,
        llm_callable: Callable[[str], str],
        registry: ToolGroupRegistry,
        ingestor: Optional[MemoryIngestor] = None,
        knowledge=None,  # Optional[ToolKnowledgeConsolidator]
        max_steps: int = DEFAULT_MAX_STEPS,
        report_max_tokens: int = DEFAULT_REPORT_MAX_TOKENS,
        observation_tokens: int = DEFAULT_OBSERVATION_TOKENS,
        progress_callback: Optional[Callable[[str], None]] = None,
    ):
        """`knowledge`: a ToolKnowledgeConsolidator. When wired, every run
        that made tool calls is followed by one micro belief-formation
        pass (same model, fresh context), and each new run's manifest
        carries the promoted statements earlier runs earned.

        `progress_callback`: called with a one-line status per subagent
        step ("[files] step 3/10: read_file"). Everything here is
        synchronous, so this is the 'still working' signal a harness can
        surface while a long tool run holds the turn."""
        self.llm = llm_callable
        self.registry = registry
        self._ingestor = ingestor
        self._knowledge = knowledge
        self.max_steps = max_steps
        self.report_max_tokens = report_max_tokens
        self.observation_tokens = observation_tokens
        self.progress_callback = progress_callback
        # Nested orchestrators for composite groups, built lazily per group.
        self._nested_orchestrators: Dict[str, Any] = {}
        # Session stats, surfaced by the dashboard.
        self.stats = {"runs": 0, "tool_calls": 0, "last_group": None,
                      "last_status": None, "learned": 0}

    # -- main-agent side -----------------------------------------------------

    def maybe_dispatch(self, model_output: str, session_id: Optional[str] = None,
                       turn_id: Optional[str] = None) -> Optional[str]:
        """Checks a main-agent output for a tool-group request; runs it
        when present. Returns the report message to append to the main
        window, or None when the output wasn't a tool-group call."""
        action = parse_json_action(model_output)
        if not action or "tool_group" not in action:
            return None
        group_name = str(action.get("tool_group", ""))
        task = str(action.get("task", ""))
        return self.run(group_name, task, session_id=session_id, turn_id=turn_id)

    # -- subagent loop -------------------------------------------------------

    def run(self, group_name: str, task: str, session_id: Optional[str] = None,
            turn_id: Optional[str] = None, context_notes: str = "") -> str:
        """Executes one task against one group. Always returns a report
        string (errors included) bounded by report_max_tokens. When a
        knowledge consolidator is wired, a micro belief-formation pass
        follows any run that made tool calls.

        context_notes: results from earlier subagents in the same
        orchestrated request (the shared scratchpad), so an ordered task
        can build on its predecessors. Clamped, never ingested here."""
        group = self.registry.get(group_name)
        self.stats["runs"] += 1
        self.stats["last_group"] = group_name
        if not group:
            self.stats["last_status"] = "unknown_group"
            known = ", ".join(self.registry.group_names()) or "none"
            return f"[TOOL REPORT: {group_name}] Unknown tool group. Available: {known}."

        if isinstance(group, CompositeToolGroup):
            return self._run_composite(group, task, context_notes,
                                       session_id, turn_id)

        learned = self._knowledge.promoted_statements(group_name) if self._knowledge else None
        manifest = self.registry.subagent_manifest(group_name, learned=learned)
        if context_notes:
            clamped = context_notes
            if count_text_tokens(clamped) > self.observation_tokens:
                clamped = chunk_text(clamped, self.observation_tokens)[0] + " [...]"
            manifest = f"{manifest}\n\nEARLIER RESULTS (from preceding subagents):\n{clamped}"
        tool_calls: List[tuple] = []
        report = self._run_loop(group, manifest, task, tool_calls, session_id, turn_id)

        if self._knowledge and tool_calls and self.stats["last_status"] != "llm_error":
            try:
                self.stats["learned"] += self._knowledge.learn_from_run(
                    group_name,
                    [t.name for t in group.tools],
                    task, tool_calls, report,
                )
            except Exception as e:
                logger.warning("Tool-knowledge pass failed (run unaffected): %s", e)

        return report

    def _run_composite(self, group: CompositeToolGroup, task: str,
                       context_notes: str, session_id: Optional[str],
                       turn_id: Optional[str]) -> str:
        """Delegates a composite group's task to its sub-orchestrator: a
        nested planner divides the task across the subgroups, nested
        subagents run sequentially, and the nested tail summary comes back
        as this group's report. Shares this runner's model, ingestor,
        knowledge, and budgets — only the registry narrows."""
        orchestrator = self._nested_orchestrators.get(group.name)
        if orchestrator is None:
            from mrag.adapters.tool_orchestrator import ToolOrchestrator
            nested_runner = SubAgentToolRunner(
                self.llm, group.registry,
                ingestor=self._ingestor,
                knowledge=self._knowledge,
                max_steps=self.max_steps,
                report_max_tokens=self.report_max_tokens,
                observation_tokens=self.observation_tokens,
                progress_callback=self.progress_callback,
            )
            orchestrator = ToolOrchestrator(
                self.llm, nested_runner,
                knowledge=self._knowledge,
                report_max_tokens=self.report_max_tokens,
            )
            self._nested_orchestrators[group.name] = orchestrator

        request = task if not context_notes else (
            f"{task}\n\nEARLIER RESULTS (from preceding subagents):\n{context_notes}")
        report = orchestrator.handle(request, session_id=session_id, turn_id=turn_id)
        self.stats["last_status"] = "ok"
        # Nested runner stats roll up so the dashboard counts all activity.
        nested = orchestrator.runner.stats
        self.stats["tool_calls"] += nested["tool_calls"]
        self.stats["learned"] += nested["learned"]
        nested["tool_calls"] = 0
        nested["learned"] = 0
        return report

    def _run_loop(self, group: ToolGroup, manifest: str, task: str,
                  tool_calls: List[tuple], session_id: Optional[str],
                  turn_id: Optional[str]) -> str:
        group_name = group.name
        transcript: List[str] = []
        parse_failures = 0

        for step in range(self.max_steps):
            if self.progress_callback:
                try:
                    self.progress_callback(
                        f"[{group_name}] step {step + 1}/{self.max_steps}: thinking")
                except Exception:
                    pass
            prompt = self._build_prompt(manifest, task, transcript)
            try:
                output = self.llm(prompt)
            except Exception as e:
                logger.warning("Subagent LLM call failed: %s", e)
                self.stats["last_status"] = "llm_error"
                return self._clamp_report(
                    f"[TOOL REPORT: {group_name}] Task not completed — model error: {e}. "
                    f"Steps taken: {len(transcript)}."
                )

            action = parse_json_action(output)
            if action is None:
                parse_failures += 1
                if parse_failures >= 2:
                    # Two unparseable turns: treat the raw output as the report
                    # rather than looping a model that can't speak the protocol.
                    self.stats["last_status"] = "protocol_fallback"
                    return self._clamp_report(f"[TOOL REPORT: {group_name}] {output.strip()}")
                transcript.append(
                    "SYSTEM: Your last response was not valid JSON. Respond with exactly one "
                    'JSON object: {"tool": "<name>", "args": {...}} or {"final_report": "..."}.'
                )
                continue

            if "final_report" in action:
                self.stats["last_status"] = "ok"
                return self._clamp_report(
                    f"[TOOL REPORT: {group_name}] {str(action['final_report']).strip()}"
                )

            tool_name = str(action.get("tool", ""))
            args = action.get("args") or {}
            tool = group.get_tool(tool_name)
            if tool is None:
                transcript.append(
                    f"SYSTEM: No tool named '{tool_name}' in this group. "
                    f"Available: {', '.join(t.name for t in group.tools)}."
                )
                continue

            if self.progress_callback:
                try:
                    self.progress_callback(
                        f"[{group_name}] step {step + 1}/{self.max_steps}: {tool_name}")
                except Exception:
                    pass
            observation = self._execute(tool, args if isinstance(args, dict) else {})
            self.stats["tool_calls"] += 1
            self._remember_observation(tool, args, observation, session_id, turn_id)

            shown = observation
            if count_text_tokens(shown) > self.observation_tokens:
                pieces = chunk_text(shown, self.observation_tokens)
                shown = pieces[0] + "\n[...truncated in this transcript; full return stored in memory...]"
            tool_calls.append((tool_name, json.dumps(args), shown))
            transcript.append(f"TOOL {tool_name}({json.dumps(args)}) RETURNED:\n{shown}")

        # Step budget exhausted: an explicitly marked INCOMPLETE report,
        # so the orchestrator's extension policy can decide what to do
        # with it (extend, carry the partial forward, or move on).
        self.stats["last_status"] = "max_steps"
        summary = "; ".join(t.splitlines()[0][:80] for t in transcript[-4:])
        return self._clamp_report(
            f"[TOOL REPORT: {group_name}] {INCOMPLETE_MARKER} — step limit "
            f"reached before the task finished. Progress so far: {summary}"
        )

    def _build_prompt(self, manifest: str, task: str, transcript: List[str]) -> str:
        history = "\n\n".join(transcript) if transcript else "(no steps taken yet)"
        return f"""Complete the task using the tools below, then write a final report.

{manifest}

RULES:
- Respond with exactly ONE JSON object per turn, nothing else.
- To call a tool: {{"tool": "<name>", "args": {{...}}}}
- When done (or when the task is impossible): {{"final_report": "<concise report of findings/results for the main agent>"}}
- The final report must contain the actual information found, not a description of it.

TASK: {task}

STEPS SO FAR:
{history}

Your JSON:"""

    def _execute(self, tool: Tool, args: Dict[str, Any]) -> str:
        try:
            result = tool.handler(**args)
        except TypeError as e:
            return f"ERROR: bad arguments for {tool.name}: {e}"
        except Exception as e:
            return f"ERROR: {tool.name} failed: {e}"
        if isinstance(result, str):
            return result
        try:
            return json.dumps(result, default=str)
        except Exception:
            return str(result)

    def _remember_observation(self, tool: Tool, args: Dict[str, Any], observation: str,
                              session_id: Optional[str], turn_id: Optional[str]):
        """Ingests informational tool returns into Layer 1 memory, verbatim.

        Bare confirmations aren't memories; anything carrying new
        information is stored with the tool call as provenance so
        retrieval can quote it later, exactly like conversational text.
        """
        if self._ingestor is None or observation.startswith("ERROR:"):
            return
        informational = tool.informational
        if informational is None:
            informational = count_text_tokens(observation) > CONFIRMATION_TOKEN_THRESHOLD
        if not informational:
            return
        text = f"{tool.name}({json.dumps(args, default=str)}) returned: {observation}"
        self._ingestor.add_event(
            text,
            source=SOURCE_TOOL_RETURN,
            session_id=session_id,
            turn_id=turn_id,
        )

    def _clamp_report(self, report: str) -> str:
        """The report must fit the main agent's chunk-size contract."""
        if count_text_tokens(report) <= self.report_max_tokens:
            return report
        pieces = chunk_text(report, self.report_max_tokens)
        return pieces[0] + "\n[...report truncated to fit the context budget...]"

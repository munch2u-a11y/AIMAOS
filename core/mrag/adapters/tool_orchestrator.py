"""Single-tool orchestration: the main agent calls one tool, ever.

The main agent's window carries one call format and a one-line capability
hint — nothing else. A request flows through three stages, all on the
same local model, all sequential (one generation in flight at a time):

1. **Plan** (own context): the orchestrator sees the group briefs and the
   promoted tool-knowledge statements — never conversational memories or
   beliefs; routing decisions need tool facts, not user history — and
   splits the request into an ordered task list, one group per task.
2. **Execute**: each task runs through SubAgentToolRunner in its own
   fresh context. Every finished report is appended to a shared
   scratchpad, and each later subagent receives the scratchpad so ordered
   tasks can build on earlier results.
3. **Summarize** (own context): once the last subagent finishes, the
   tail-end pass reduces the scratchpad to a single reply — shaped by the
   main agent's original request and clamped to the chunk token limit —
   which is what re-enters the main agent's rolling window. When a single
   task already produced a fitting report, the pass is skipped (no LLM
   call spent restating one report).

Informational tool returns were already ingested into Layer 1 by the
runner during execution, so the summarized reply is a working-window
convenience — the full evidence stays retrievable.
"""

import logging
from typing import List, Optional, Tuple

from mrag.adapters.tool_groups import (
    INCOMPLETE_MARKER, SubAgentToolRunner, parse_json_action,
)
from mrag.adapters.tool_knowledge import _parse_json_array
from mrag.core.memory_ingestor import chunk_text
from mrag.core.token_counting import count_text_tokens

logger = logging.getLogger("mrag.adapters.tool_orchestrator")

DEFAULT_MAX_TASKS = 5
# Ceiling on the tool-knowledge block in the planning prompt.
PLANNING_KNOWLEDGE_MAX_TOKENS = 150

_PLAN_PROMPT = """Split this tool request into an ordered task list for tool subagents.

TOOL GROUPS:
{groups}
{knowledge}
REQUEST: {request}

Rules:
- 1 to {max_tasks} tasks; each task is handled by exactly one group.
- Each task is an OUTCOME the group's subagent must achieve, not a single
  tool operation — a subagent can use several tools over many steps
  (e.g. "fix the bug in calc.py so test_calc.py passes", never "read calc.py").
- Prefer FEWER, bigger tasks; add a task only when a different group is needed.
- Each task description must be self-contained and specific.
- Order tasks so later ones can build on earlier results.
Output only a JSON array: [{{"group": "<group name>", "task": "<task>"}}]"""

_SUMMARY_PROMPT = """Subagent reports for a tool request follow. Write the single reply to send back.

REQUEST: {request}

REPORTS:
{scratchpad}

Keep only what answers the request; keep every specific value (names, numbers, dates) exactly; under {target_words} words. Output only the reply."""


class ToolOrchestrator:
    """One entry point for all tool use. See module docstring."""

    def __init__(
        self,
        llm_callable,
        runner: SubAgentToolRunner,
        knowledge=None,  # Optional[ToolKnowledgeConsolidator]
        max_tasks: int = DEFAULT_MAX_TASKS,
        report_max_tokens: Optional[int] = None,
        max_task_extensions: int = 1,
    ):
        """max_task_extensions: when a subagent comes back INCOMPLETE
        (step budget exhausted mid-task), the orchestrator — as the task
        manager responsible — re-dispatches the same task up to this many
        times with the partial progress as continuation context. A task
        still incomplete after its extensions is carried forward as a
        partial: the tail summary reports it honestly rather than
        pretending it finished."""
        self.llm = llm_callable
        self.runner = runner
        self._knowledge = knowledge
        self.max_tasks = max_tasks
        self.report_max_tokens = report_max_tokens or runner.report_max_tokens
        self.max_task_extensions = max_task_extensions
        self.stats = {"requests": 0, "tasks_planned": 0, "summaries": 0,
                      "extensions": 0, "incomplete_tasks": 0, "last_plan": []}

    # -- Layer A: the only tool text the main agent ever holds ------------

    def main_agent_brief(self) -> str:
        summaries = ", ".join(
            f"{name} ({self.runner.registry.get(name).summary})"
            for name in self.runner.registry.group_names()
        ) or "none"
        return (
            f"Tools available: {summaries}.\n"
            'To use them respond with exactly: '
            '{"tool_request": "<what you need done, with all specifics>"}'
        )

    def maybe_dispatch(self, model_output: str, session_id: Optional[str] = None,
                       turn_id: Optional[str] = None) -> Optional[str]:
        """Checks main-agent output for a tool request; orchestrates it
        when present. Returns the reply to append to the main window, or
        None when the output wasn't a tool request."""
        action = parse_json_action(model_output)
        if not action:
            return None
        if "tool_request" in action:
            return self.handle(str(action["tool_request"]),
                               session_id=session_id, turn_id=turn_id)
        if "tool_group" in action:  # direct-group form still honored
            return self.runner.run(str(action.get("tool_group", "")),
                                   str(action.get("task", "")),
                                   session_id=session_id, turn_id=turn_id)
        return None

    # -- pipeline ----------------------------------------------------------

    def handle(self, request: str, session_id: Optional[str] = None,
               turn_id: Optional[str] = None) -> str:
        self.stats["requests"] += 1
        request = (request or "").strip()
        if not request:
            return "[TOOL REPORT] Empty tool request."

        tasks = self._plan(request)
        if not tasks:
            return ("[TOOL REPORT] Could not plan the request against the "
                    f"available groups ({', '.join(self.runner.registry.group_names())}).")
        self.stats["tasks_planned"] += len(tasks)
        self.stats["last_plan"] = [f"{group}: {task}" for group, task in tasks]

        # Ordered execution over a shared scratchpad: each subagent gets a
        # fresh context plus the results of everything before it. An
        # INCOMPLETE report triggers the extension policy: re-dispatch the
        # same task with the partial progress as continuation context, up
        # to max_task_extensions; a task that still doesn't finish is
        # carried forward as an explicit partial.
        scratchpad: List[str] = []
        any_incomplete = False
        for index, (group, task) in enumerate(tasks):
            notes = "\n\n".join(scratchpad)
            report = self.runner.run(group, task, session_id=session_id,
                                     turn_id=turn_id, context_notes=notes)
            extensions_left = self.max_task_extensions
            while INCOMPLETE_MARKER in report and extensions_left > 0:
                extensions_left -= 1
                self.stats["extensions"] += 1
                continuation = (f"{notes}\n\n{report}" if notes else report)
                report = self.runner.run(
                    group,
                    f"Continue this unfinished task and complete it: {task}",
                    session_id=session_id, turn_id=turn_id,
                    context_notes=continuation)
            if INCOMPLETE_MARKER in report:
                any_incomplete = True
                self.stats["incomplete_tasks"] += 1
            scratchpad.append(f"[{index + 1}/{len(tasks)} {group}] {report}")

        combined = "\n\n".join(scratchpad)
        # Single fitting complete report: return it as-is, no summary call.
        if (len(tasks) == 1 and not any_incomplete
                and count_text_tokens(combined) <= self.report_max_tokens):
            return combined

        return self._summarize(request, combined, any_incomplete=any_incomplete)

    def _plan(self, request: str) -> List[Tuple[str, str]]:
        registry = self.runner.registry
        group_names = registry.group_names()
        if not group_names:
            return []

        group_lines = "\n".join(
            f"- {name}: {registry.get(name).summary}" for name in group_names
        )
        knowledge_block = self._planning_knowledge(group_names)
        prompt = _PLAN_PROMPT.format(
            groups=group_lines,
            knowledge=knowledge_block,
            request=request,
            max_tasks=self.max_tasks,
        )
        try:
            output = self.llm(prompt)
        except Exception as e:
            logger.warning("Planning call failed: %s", e)
            output = ""

        tasks: List[Tuple[str, str]] = []
        for entry in _parse_json_array(output) or []:
            if not isinstance(entry, dict):
                continue
            group = str(entry.get("group", "")).strip()
            task = str(entry.get("task", "")).strip()
            if group in group_names and task:
                tasks.append((group, task))
        tasks = tasks[: self.max_tasks]

        if not tasks and len(group_names) == 1:
            # One group means routing is trivial — don't fail a request
            # because a small model flubbed the planning JSON.
            tasks = [(group_names[0], request)]
        return tasks

    def _planning_knowledge(self, group_names: List[str]) -> str:
        """The tool-derived knowledge the planner sees — and the ONLY
        memory it sees. Promoted statements help routing (which tool can
        actually do what); conversational beliefs would be noise here."""
        if self._knowledge is None:
            return ""
        lines: List[str] = []
        spent = 0
        for group in group_names:
            for tool_name, statements in self._knowledge.promoted_statements(group).items():
                for statement in statements:
                    line = f"- {tool_name}: {statement}"
                    tokens = count_text_tokens(line)
                    if spent + tokens > PLANNING_KNOWLEDGE_MAX_TOKENS:
                        break
                    lines.append(line)
                    spent += tokens
        if not lines:
            return ""
        return "\nKNOWN TOOL BEHAVIOR (from prior runs):\n" + "\n".join(lines) + "\n"

    def _summarize(self, request: str, scratchpad: str,
                   any_incomplete: bool = False) -> str:
        self.stats["summaries"] += 1
        target_words = int(self.report_max_tokens * 0.7)
        if any_incomplete:
            request += ("\n(Note: at least one subtask did not finish — state "
                        "clearly what was completed and what remains undone.)")
        prompt = _SUMMARY_PROMPT.format(
            request=request, scratchpad=scratchpad, target_words=target_words,
        )
        try:
            summary = self.llm(prompt).strip()
        except Exception as e:
            logger.warning("Tail summarization failed, truncating scratchpad: %s", e)
            summary = ""
        if not summary:
            summary = scratchpad
        report = f"[TOOL REPORT] {summary}"
        if count_text_tokens(report) > self.report_max_tokens:
            report = chunk_text(report, self.report_max_tokens)[0] + \
                "\n[...truncated to fit the context budget...]"
        return report

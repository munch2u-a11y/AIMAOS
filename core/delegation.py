"""
AIMAOS Delegation Layer — every tool is a specialized subagent.

The tool-calling pipeline is decomposed so each stage gets a full context
window focused on exactly one job:

  Main agent          reasons over the WHOLE task with a dynamic capability
                      list (beliefs about what it can do — never raw tool
                      schemas, never raw tool output). Delegates a parsed-down
                      directive to a domain orchestrator.

  Orchestrator        one per capability domain. Spends its entire context on
  subagent            that domain: re-queries the owner's mRAG store for the
                      tool-use beliefs that couldn't compete for space in the
                      main agent's whole-task injection, then briefs specific
                      tool subagents with high specificity.

  Tool subagent       wraps ONE tool. Its system prompt is mostly the tool
                      schema plus the owner's accumulated beliefs about HOW
                      this tool works (skills/lessons) — deliberately NOT a
                      "You are the..." persona. It formulates the exact call,
                      executes it, and chunk-summarizes oversized output.

  Return summarizer   compresses the orchestrator's transcript into an
                      optimized first-person report — the only text the main
                      agent ever sees. Verbatim tool output is logged to the
                      owner's tool_logs for the record (Kai's archives are the
                      permanent home).

Every stage records experiences into the owner's belief store, so HOW an
agent uses its tools — what works, what fails — becomes the substance of its
evolving identity.
"""
import os

def _find_aimaos_root():
    p = os.path.dirname(os.path.abspath(__file__))
    while p != os.path.dirname(p) and not os.path.exists(os.path.join(p, "aimaos_config.yaml")):
        p = os.path.dirname(p)
    return p
AIMAOS_ROOT = os.environ.get("AIMAOS_ROOT") or _find_aimaos_root()
import sys
import json
import yaml
import logging
import importlib.util
from datetime import datetime

logger = logging.getLogger(__name__)

# Raw tool output longer than this is chunk-summarized by the tool subagent
# before anything upstream sees it.
SUMMARIZE_THRESHOLD_CHARS = 1500
CHUNK_CHARS = 3500


def load_capabilities(agent_name):
    """Loads the agent's capability domains from <Agent>-AI/capabilities.yaml.
    Tool entries are stored office-root-relative for portability and resolved
    to absolute paths here (absolute entries pass through unchanged)."""
    path = os.path.join(AIMAOS_ROOT, f"{agent_name}-AI", "capabilities.yaml")
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r") as f:
            data = yaml.safe_load(f) or {}
        for domain_cfg in (data.get("domains") or {}).values():
            tools = domain_cfg.get("tools") or []
            domain_cfg["tools"] = [
                t if os.path.isabs(t) else os.path.join(AIMAOS_ROOT, t)
                for t in tools
            ]
        return data
    except Exception as e:
        logger.warning(f"[{agent_name}] failed to load capabilities: {e}")
        return {}


def load_tool_module(tool_path):
    """Loads a tool module (TOOL_DEFINITION + execute) by absolute path."""
    name = f"aimaos_deleg_{os.path.basename(os.path.dirname(tool_path))}_{os.path.splitext(os.path.basename(tool_path))[0]}"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, tool_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def gather_tool_beliefs(owner, query_text, limit_tokens=None):
    """Pulls the owner's relevant tool-use beliefs (skills, lessons, memories)
    for a query. This is the mechanism that turns accumulated experience into
    subagent system prompts."""
    try:
        owner.injector.sync_index()
        injected = owner.injector.inject(trigger_text=query_text)
        return injected or ""
    except Exception as e:
        logger.warning(f"[{owner.name}] belief gathering failed: {e}")
        return ""


class ToolSubagent:
    """A specialist wrapping exactly one tool. Minimalist prompt: schema +
    the owner's beliefs about how this tool works. No persona."""

    def __init__(self, owner, tool_path):
        self.owner = owner
        self.tool_path = tool_path
        self.module = load_tool_module(tool_path)
        self.definition = self.module.TOOL_DEFINITION
        self.name = self.definition["name"]
        self.log_dir = os.path.join(owner.workspace_dir, "workspace", ".memory", "tool_logs")
        os.makedirs(self.log_dir, exist_ok=True)

    def system_prompt(self, directive):
        beliefs = gather_tool_beliefs(self.owner, f"{self.name} {directive}")
        prompt = (
            f"Task focus: operate the `{self.name}` tool for {self.owner.name}'s office work.\n"
            f"Tool schema:\n{json.dumps(self.definition, indent=1)}\n"
        )
        if beliefs:
            prompt += f"\nKnown from experience (how this tool actually behaves):\n{beliefs}\n"
        prompt += (
            "\nFormulate the single best tool call for the directive. "
            "Call the tool; do not describe it."
        )
        return prompt

    def _log_verbatim(self, directive, arguments, raw_output):
        """Log provenance under the configured privacy policy.

        Raw output storage is off by default for the public beta; a digest and
        length retain auditability without creating an indefinite PII copy.
        """
        from core.privacy import privacy_safe_tool_record, redact_sensitive
        entry = {
            "timestamp": datetime.now().isoformat(),
            "agent": self.owner.name,
            "tool": self.name,
            "directive": redact_sensitive(directive),
            "arguments": json.loads(redact_sensitive(json.dumps(arguments, default=str))),
        }
        entry.update(privacy_safe_tool_record(raw_output))
        path = os.path.join(self.log_dir,
                            f"{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}_{self.name}.json")
        try:
            with open(path, "w") as f:
                json.dump(entry, f, indent=2)
        except Exception as e:
            logger.warning(f"[{self.owner.name}/{self.name}] verbatim log failed: {e}")
        return path

    def _summarize_output(self, directive, raw_output):
        """Chunk-summarizes oversized raw output so upstream context stays
        focused. Each chunk gets its own bounded LLM pass."""
        text = str(raw_output)
        if len(text) <= SUMMARIZE_THRESHOLD_CHARS:
            return text

        chunks = [text[i:i + CHUNK_CHARS] for i in range(0, len(text), CHUNK_CHARS)]
        notes = []
        for idx, chunk in enumerate(chunks[:6]):  # hard cap: 6 chunks
            try:
                resp = self.owner.llm.chat([
                    {"role": "system", "content":
                        f"Task focus: extract only what matters from `{self.name}` output "
                        f"for this directive: {directive}"},
                    {"role": "user", "content":
                        f"Output part {idx + 1}/{len(chunks)}:\n{chunk}\n\n"
                        "List the facts, values, paths, or errors relevant to the directive. "
                        "Terse bullet points only."},
                ])
                notes.append((resp.content or "").strip())
            except Exception as e:
                notes.append(f"(chunk {idx + 1} summary failed: {e})")
        joined = "\n".join(n for n in notes if n)
        return f"[Condensed from {len(text)} chars of tool output]\n{joined}"

    def run(self, directive):
        """One tool-subagent thought: formulate the call from schema+beliefs,
        execute, condense, record the experience. Returns compact result text."""
        messages = [
            {"role": "system", "content": self.system_prompt(directive)},
            {"role": "user", "content": f"Directive: {directive}"},
        ]
        try:
            resp = self.owner.llm.chat(messages, tools=[self.definition])
        except Exception as e:
            return f"({self.name} subagent could not reach the model: {e})"

        if not resp.tool_calls:
            # The specialist chose not to call — surface its reasoning as-is.
            return (resp.content or f"({self.name} subagent made no call)").strip()

        tc = resp.tool_calls[0]
        arguments = tc.get("arguments") or {}
        from core.security import tool_execution_policy
        allowed, policy_message = tool_execution_policy(self.name, arguments)
        if not allowed:
            self.owner.record_experience(
                f"Security policy blocked {self.name}: {policy_message}",
                category="memory", confidence=0.8, source=f"policy_{self.name}")
            return f"SECURITY POLICY: {policy_message}"
        try:
            raw = self.module.execute(**arguments)
            outcome = "ok"
        except TypeError as e:
            raw = f"Argument error calling {self.name}: {e}"
            outcome = "bad_arguments"
        except Exception as e:
            raw = f"{self.name} raised: {e}"
            outcome = "error"

        log_path = self._log_verbatim(directive, arguments, raw)
        condensed = self._summarize_output(directive, raw)

        # The experience IS the identity: record how this use of the tool went.
        from core.privacy import redact_sensitive
        self.owner.record_experience(
            redact_sensitive(f"Used {self.name} with {json.dumps(arguments)[:160]} -> {outcome}. "
                              f"Result gist: {str(condensed)[:180]}"),
            category="memory", confidence=0.6, source=f"tool_{self.name}")

        return f"{condensed}\n(tool audit record: {os.path.basename(log_path)})"


class OrchestratorSubagent:
    """Owns one capability domain. Its whole context is the domain: the
    directive, the domain's tool subagents, and the owner's domain-relevant
    beliefs re-pulled from the same mRAG pool the main agent uses."""

    MAX_ROUNDS = 3

    def __init__(self, owner, domain_name, domain_cfg):
        self.owner = owner
        self.domain = domain_name
        self.description = domain_cfg.get("description", domain_name)
        self.subagents = {}
        for tool_path in domain_cfg.get("tools", []):
            try:
                sa = ToolSubagent(owner, tool_path)
                self.subagents[sa.name] = sa
            except Exception as e:
                logger.warning(f"[{owner.name}/{domain_name}] tool load failed ({tool_path}): {e}")

    def _meta_tool_defs(self):
        """The orchestrator does not see raw schemas either — it sees one
        directive-taking meta-tool per specialist, described by the tool's
        purpose. The specialist itself formulates exact arguments."""
        defs = []
        for name, sa in self.subagents.items():
            defs.append({
                "name": name,
                "description": sa.definition.get("description", name)[:300],
                "parameters": {
                    "type": "object",
                    "properties": {
                        "directive": {
                            "type": "string",
                            "description": "Precise instruction for this specialist: what to do, "
                                           "with every concrete detail it needs (names, paths, values)."
                        }
                    },
                    "required": ["directive"],
                },
            })
        return defs

    def system_prompt(self, directive):
        # Domain-scoped belief pull: query with the directive + this domain's
        # tool names so beliefs that lost the fight for the main agent's
        # context get their chance here.
        beliefs = gather_tool_beliefs(
            self.owner, f"{directive} {self.domain} {' '.join(self.subagents)}")
        prompt = (
            f"Task focus: the '{self.domain}' capability of {self.owner.name}'s office work — "
            f"{self.description}\n"
            f"Available specialists: {', '.join(self.subagents) or 'none'}.\n"
        )
        if beliefs:
            prompt += f"\nKnown from experience in this domain:\n{beliefs}\n"
        prompt += (
            "\nFirst, state the minimal sequence of specialist calls that fulfills the directive as a "
            "short plan. Give each specialist a fully-specified directive. Once you have every "
            "specialist's result, reply with plain text stating ONLY what those results actually "
            "confirm happened — if a result doesn't confirm something succeeded, say it's unconfirmed "
            "or failed rather than assuming it went through. Never state something was done unless a "
            "specialist's result above actually shows it."
        )
        return prompt

    def run(self, directive):
        """Executes the domain work, then hands the transcript to the return
        summarizer. Returns the optimized first-person report."""
        if not self.subagents:
            return f"(domain '{self.domain}' has no working specialists)"

        messages = [
            {"role": "system", "content": self.system_prompt(directive)},
            {"role": "user", "content": f"Directive from {self.owner.name}: {directive}"},
        ]
        transcript = []
        for _ in range(self.MAX_ROUNDS):
            try:
                resp = self.owner.llm.chat(messages, tools=self._meta_tool_defs())
            except Exception as e:
                transcript.append(f"orchestrator model error: {e}")
                break

            if not resp.tool_calls:
                if resp.content:
                    transcript.append(f"orchestrator conclusion: {resp.content.strip()}")
                break

            messages.append({"role": "assistant", "content": resp.content or "",
                             "tool_calls": resp.tool_calls})
            for tc in resp.tool_calls:
                name = tc["name"]
                sub_directive = (tc.get("arguments") or {}).get("directive", directive)
                sa = self.subagents.get(name)
                result = sa.run(sub_directive) if sa else f"(no specialist named {name})"
                transcript.append(f"[{name}] directive: {sub_directive}\n[{name}] result: {result}")
                messages.append({"role": "tool", "content": str(result),
                                 "name": name, "tool_call_id": tc.get("id")})

        return self._summarize_return(directive, transcript)

    def _summarize_return(self, directive, transcript):
        """The return orchestrator: compress everything into the optimized
        first-person report that is ALL the main agent will ever see."""
        joined = "\n\n".join(transcript) if transcript else "(no specialist activity)"
        try:
            resp = self.owner.llm.chat([
                {"role": "system", "content":
                    f"Task focus: report back to {self.owner.name} on delegated "
                    f"'{self.domain}' work, first person past tense. Ground the report "
                    f"STRICTLY in what the transcript below actually shows — never say a "
                    f"step succeeded (a file created, a message sent) unless a specialist's "
                    f"result confirms it. If a step's outcome is unclear or missing from the "
                    f"transcript, say it's unconfirmed or failed rather than assuming success."},
                {"role": "user", "content":
                    f"Original directive: {directive}\n\nWork transcript:\n{joined}\n\n"
                    "Write the report: 2-5 sentences, stating only what the transcript above "
                    "actually confirms (file paths created, key facts found, exact errors), "
                    "and calling out anything unconfirmed or failed. No raw output, no tool jargon."},
            ])
            report = (resp.content or "").strip()
        except Exception:
            report = ""
        if not report:
            # Fall back to the compact transcript rather than losing the work.
            report = joined[:1200]
        return report

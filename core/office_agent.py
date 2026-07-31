"""
OfficeAgent — the shared kernel for AIMAOS roster mini-agents.

Each roster agent (Alix, Kai, Marley, Quinn, Zoe, Finn, Rae) runs as an
independent Helix-style mini-agent:

  1. Ultra-minimal system prompt: identity line + the agent's *heaviest
     evolved belief* from its own private mRAG belief store — not a static
     hardcoded string.
  2. Real single-thought turns: each turn takes one Office Board task,
     thinks with a local LLM, executes the tool calls the model makes,
     and posts the genuine result back to the board.
  3. Identity evolution: every completed turn records experience beliefs
     into the agent's own store; periodic reflection turns distill those
     experiences into opinions and identity premises via the LLM, so each
     agent's beliefs — and therefore its future prompts — diverge over time.
  4. Failure model: turns that error mark the task "failed" with the error
     recorded; the office daemon handles retry/requeue.
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
from datetime import datetime

sys.path.insert(0, AIMAOS_ROOT)

from core.comms.bus import AgentCompanyBus
from core.comms.office_board import OfficeBoard
from core.mrag_beliefs import AgentBeliefStore, DEFAULT_BELIEFS
from core.llm import LLMClient
from core.tools import ToolRegistry
from core.mrag.memory.belief_store import BeliefStore
from core.mrag.core.vector_store import DummyVectorStore
from core.mrag.core.pre_generative_injection import PreGenerativeInjector

logger = logging.getLogger(__name__)

OFFICE_CONFIG_PATH = os.path.join(AIMAOS_ROOT, "aimaos_config.yaml")

# Identity-bearing categories for the minimal prompt. Skills lead: an
# agent's beliefs about HOW it operates — which tools work, which approaches
# fail — ARE its identity. Self-descriptive premises/preferences form
# naturally through mRAG corroboration and are never forced.
IDENTITY_CATEGORIES = ("skills", "premises", "preferences", "propositions")


def load_office_config():
    try:
        with open(OFFICE_CONFIG_PATH, "r") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


class OfficeAgent:
    def __init__(self, name, role=None, config=None):
        self.name = name
        office_cfg = load_office_config()
        agent_cfg = office_cfg.get("agents", {}).get(name, {})
        self.office_settings = office_cfg.get("office", {})
        self.role = role or agent_cfg.get("role", f"{name} Office Agent")
        self.config = config or {}

        llm_cfg = dict(office_cfg.get("llm", {}))
        llm_cfg["model"] = (self.config.get("model")
                           or agent_cfg.get("model")
                           or llm_cfg.get("default_model", "qwen3.5:2b"))
        self.model = llm_cfg["model"]
        self.llm = LLMClient({"llm": llm_cfg})

        self.workspace_dir = os.path.join(AIMAOS_ROOT, f"{name}-AI")
        self.bus = AgentCompanyBus(name)
        self.board = OfficeBoard()

        # Compat bridge: the shared office-wide belief snapshot other
        # components (web UI, Finn chat) read. Reflection syncs the evolved
        # heaviest belief back into it.
        self.belief_store = AgentBeliefStore()

        # The agent's OWN identity engine: private mRAG belief store +
        # injector, isolated in its workspace.
        mrag_dir = os.path.join(self.workspace_dir, "workspace", ".memory", "mrag_data")
        self.identity_store = BeliefStore(data_dir=mrag_dir)
        from core.mrag.core.vector_store import create_vector_store
        v_backend = self.office_settings.get("vector_store", os.environ.get("MRAG_VECTOR_STORE", "dummy"))
        try:
            self.vector_store = create_vector_store(v_backend)
        except Exception:
            self.vector_store = DummyVectorStore()
        self.injector = PreGenerativeInjector(
            belief_store=self.identity_store,
            vector_store=self.vector_store,
            max_injected_tokens=int(self.office_settings.get("injection_max_tokens", 400)),
        )

        tools_dir = os.path.join(self.workspace_dir, "tools")
        self.tools = ToolRegistry(tools_dir) if os.path.isdir(tools_dir) else None

        # Delegation layer: capability domains -> orchestrator subagents.
        # The main agent reasons over capability BELIEFS, not tool schemas.
        from core.delegation import load_capabilities
        caps = load_capabilities(name)
        self.domains = caps.get("domains", {})
        self.delegation_enabled = bool(self.domains) and bool(
            self.office_settings.get("delegation", True))
        self._seed_capability_beliefs(caps.get("seed_beliefs", []))
        # Transcript of the most recent main-agent turn, kept for benchmarks
        # verifying that raw tool output never enters the main context.
        self.last_turn_messages = []

    def _seed_capability_beliefs(self, seeds):
        """Jumpstart tool-use beliefs. Deterministic ids make re-seeding a
        no-op; from here the store grows only from the agent's own work."""
        import hashlib
        for content in seeds:
            bid = f"seed_{hashlib.sha256(content.encode()).hexdigest()[:12]}"
            try:
                self.identity_store.add_belief(
                    category="skills", belief_id=bid, content=content,
                    confidence=0.55, source="capability_seed")
            except Exception as e:
                logger.warning(f"[{self.name}] seed belief failed: {e}")

    def _top_skill_for(self, domain_text):
        """Highest-confidence skill belief mentioning this domain's vocabulary —
        used to flavor the capability list with lived experience."""
        tokens = set(domain_text.lower().replace("_", " ").split())
        best, best_conf = None, 0.0
        try:
            for b in self.identity_store.get_all_beliefs_flat():
                if b.get("_category") != "skills":
                    continue
                content = b.get("content", "")
                if tokens & set(content.lower().split()):
                    conf = float(b.get("confidence", 0)) + float(b.get("verifications", 0)) * 0.05
                    if conf > best_conf:
                        best, best_conf = content, conf
        except Exception:
            pass
        return best

    # ------------------------------------------------------------ identity
    def get_heaviest_identity_belief(self):
        """The agent's strongest self-formed belief; falls back to the seed."""
        best, best_score = None, -1.0
        try:
            for b in self.identity_store.get_all_beliefs_flat():
                if b.get("_category") not in IDENTITY_CATEGORIES:
                    continue
                score = float(b.get("relevance", 0)) + float(b.get("confidence", 0))
                if score > best_score:
                    best, best_score = b, score
        except Exception as e:
            logger.warning(f"[{self.name}] identity store read failed: {e}")
        if best:
            content = best.get("content", "").strip()
            if content:
                return content
        return DEFAULT_BELIEFS.get(self.name, self.belief_store.get_heaviest_belief(self.name))

    def get_system_prompt(self, task_text=""):
        """Helix-style ultra-minimal prompt: identity + heaviest evolved belief,
        plus a small mRAG context injection relevant to the task at hand."""
        belief = self.get_heaviest_identity_belief()
        prompt = f"Identity: You are {self.name}, the {self.role} in AIMAOS.\nCore Belief: {belief}"
        if self.delegation_enabled and self.domains:
            abilities = "; ".join(
                f"{d.replace('_', ' ')} ({cfg.get('description', '')[:80].rstrip('.')})"
                for d, cfg in self.domains.items())
            prompt += f"\nAbilities: {abilities}"
        if task_text:
            try:
                self.injector.sync_index()
                injected = self.injector.inject(trigger_text=task_text)
                if injected:
                    prompt += f"\n{injected}"
            except Exception as e:
                logger.warning(f"[{self.name}] mRAG injection failed: {e}")
        return prompt

    def record_experience(self, content, category="memory", confidence=0.6, source=None):
        """Writes one experience into the agent's own store (no LLM needed)."""
        belief_id = f"{self.name.lower()}_{category}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
        try:
            self.identity_store.merge_or_add_belief(
                category=category,
                belief_id=belief_id,
                content=f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] {content}",
                confidence=confidence,
                source=source or f"{self.name.lower()}_turn",
                vector_store=self.vector_store,
            )
        except Exception as e:
            logger.warning(f"[{self.name}] record_experience failed: {e}")

    def reflect(self):
        """Identity reflection turn: the agent reads its recent experiences and
        distills them — with its own LLM — into a first-person opinion or
        identity premise, which is merged into its belief store. Over many
        turns this is what makes each agent's identity uniquely its own."""
        try:
            recent = [b for b in self.identity_store.get_all_beliefs_flat()
                      if b.get("_category") == "memory"][-12:]
        except Exception:
            recent = []
        if not recent:
            return f"[{self.name}] Reflection skipped: no experiences recorded yet."

        experiences = "\n".join(f"- {b.get('content', '')}" for b in recent)
        sys_prompt = (f"Identity: You are {self.name}, the {self.role} in AIMAOS.\n"
                      f"Core Belief: {self.get_heaviest_identity_belief()}")
        ask = ("Below are your own recent work experiences in the office.\n"
               f"{experiences}\n\n"
               "Reflect on HOW the work went: which tools and approaches worked, "
               "which failed, and what you would do differently. Reply with one "
               "or two lines, each formatted exactly as:\n"
               "LESSON: <one first-person sentence stating a concrete, reusable "
               "lesson about how to use a specific tool or approach effectively "
               "(or a specific way it fails)>\n"
               "Only state lessons grounded in the experiences above. Do not "
               "describe yourself; describe what works.")
        try:
            resp = self.llm.chat([
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": ask},
            ])
        except Exception as e:
            return f"[{self.name}] Reflection failed: LLM unavailable ({e})"

        text = resp.content or ""
        distilled = []
        for line in text.splitlines():
            line = line.strip()
            if line.upper().startswith("LESSON:"):
                distilled.append(("skills", line.split(":", 1)[1].strip(), 0.65))
        # Operational lessons are the identity. Self-descriptive beliefs
        # ("I prefer...", "I am...") are never forced here — they emerge on
        # their own as merge_or_add_belief corroborates repeated experience.
        for category, content, conf in distilled:
            if content:
                self.record_experience(content, category=category, confidence=conf,
                                       source=f"{self.name.lower()}_reflection")

        # Sync the evolved heaviest belief into the shared office snapshot so
        # every component sees this agent's current identity.
        evolved = self.get_heaviest_identity_belief()
        try:
            self.belief_store.update_belief(self.name, evolved)
        except Exception as e:
            logger.warning(f"[{self.name}] belief sync failed: {e}")

        return (f"[{self.name}] Reflection complete: distilled {len(distilled)} belief(s) "
                f"from {len(recent)} experiences. Current core belief: '{evolved}'")

    # ------------------------------------------------------------ execution
    def execute_single_turn(self, task_id=None):
        """One real single-thought turn: claim a board task, think with the
        LLM, execute its tool calls, post the genuine outcome."""
        tasks = self.board.get_pending_tasks_for(self.name)
        target = None
        if task_id:
            target = next((t for t in tasks if t["id"] == task_id), None)
        if target is None:
            target = tasks[0] if tasks else None
        if target is None:
            return f"[{self.name}] Single turn: no pending tasks on the Office Board."

        self.board.update_agent_status(self.name, "working")
        self.board.update_task_status(target["id"], "in_progress")
        self.board.log_activity(f"[{self.name}] Single-thought turn starting for '{target['title']}' (Model: {self.model})")

        task_text = (f"Office Board task '{target['title']}' "
                     f"(priority {target.get('priority')}, from {target.get('requester')}).\n"
                     f"Details: {json.dumps(target.get('details', {}), default=str)}")
        outcome = None
        try:
            outcome = self._llm_task_loop(task_text)
            self.board.update_task_status(target["id"], "completed", result=outcome)
            self.record_experience(
                f"I completed task '{target['title']}' for {target.get('requester')}. Outcome: {outcome[:300]}",
                category="memory", confidence=0.65)
            status_word = "completed"
        except Exception as e:
            outcome = f"Turn failed: {e}"
            self.board.update_task_status(target["id"], "failed", result=outcome)
            self.board.log_activity(f"[{self.name}] Task '{target['title']}' FAILED: {e}")
            self.record_experience(
                f"I failed task '{target['title']}': {e}", category="memory", confidence=0.6)
            status_word = "failed"
        finally:
            self.board.update_agent_status(self.name, "idle")

        return f"[{self.name}] Single-thought turn {status_word} for '{target['title']}'.\n{outcome}"

    def _delegate_tool_defs(self):
        """The main agent's ability surface: one directive-taking delegate per
        capability domain, described by domain purpose plus the agent's own
        strongest relevant skill belief. A dynamic, experience-relative list —
        not a tool schema dump."""
        defs = []
        for domain, cfg in self.domains.items():
            desc = cfg.get("description", domain)
            skill = self._top_skill_for(f"{domain} {desc}")
            if skill:
                desc = f"{desc} (From experience: {skill[:160]})"
            defs.append({
                "name": f"delegate_{domain}",
                "description": desc[:400],
                "parameters": {
                    "type": "object",
                    "properties": {
                        "directive": {
                            "type": "string",
                            "description": "Parsed-down instruction for this capability: exactly what "
                                           "is needed, with all concrete details (names, values, paths)."
                        }
                    },
                    "required": ["directive"],
                },
            })
        return defs

    def _run_delegation(self, domain, directive):
        from core.delegation import OrchestratorSubagent
        orch = OrchestratorSubagent(self, domain, self.domains[domain])
        return orch.run(directive)

    def _llm_task_loop(self, task_text):
        """Bounded reasoning loop. In delegation mode the main agent sees only
        capability delegates and receives only optimized first-person reports —
        never raw tool schemas or raw tool output."""
        sys_prompt = self.get_system_prompt(task_text)
        if self.delegation_enabled:
            tool_defs = self._delegate_tool_defs()
            ask = ("First, state a short numbered plan: the concrete steps this task actually needs. "
                   "Then delegate each step with a precise directive. Once every step has a report back, "
                   "write your completion summary grounded ONLY in what those reports actually confirm — "
                   "if a report doesn't confirm a step succeeded (a document produced, a message sent), "
                   "say that step is unconfirmed or failed rather than assuming it went through. Never "
                   "state something was done unless a report above actually shows it.")
        else:
            tool_defs = self.tools.get_tool_definitions() if self.tools else []
            ask = ("First, state a short numbered plan: the concrete steps this task actually needs. "
                   "Then work through it, using your tools when they apply. Your completion summary must "
                   "state ONLY what your tool results actually confirm — never claim a file was created, "
                   "a message was sent, or any other action succeeded unless a tool result above shows it.")
        messages = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": f"{task_text}\n\n{ask}"},
        ]
        self.last_turn_messages = messages
        max_turns = int(self.office_settings.get("max_tool_turns", 4))
        tool_results = []
        for _ in range(max_turns):
            resp = self.llm.chat(messages, tools=tool_defs if tool_defs else None)
            if resp.tool_calls:
                messages.append({"role": "assistant", "content": resp.content or "",
                                 "tool_calls": resp.tool_calls})
                for tc in resp.tool_calls:
                    name = tc["name"]
                    if self.delegation_enabled and name.startswith("delegate_"):
                        domain = name[len("delegate_"):]
                        directive = (tc.get("arguments") or {}).get("directive", task_text)
                        if domain in self.domains:
                            result = self._run_delegation(domain, directive)
                        else:
                            result = f"(no capability domain named '{domain}')"
                    elif self.tools:
                        result = self.tools.execute_tool(name, tc["arguments"])
                    else:
                        result = f"(no executor available for '{name}')"
                    tool_results.append(f"{name} -> {str(result)[:400]}")
                    messages.append({"role": "tool", "content": str(result),
                                     "name": name, "tool_call_id": tc.get("id")})
                continue
            summary = (resp.content or "").strip() or "Turn finished with no summary text."
            if tool_results:
                summary += "\n[Tools executed]\n" + "\n".join(tool_results)
            return summary

        # Tool-turn limit reached: force one final tool-free call so the turn
        # always ends with the agent's own summary of what it accomplished.
        messages.append({"role": "user", "content":
            "Stop using tools now. Summarize in 2-3 sentences ONLY what your tool results above "
            "actually show you accomplished, and what's still outstanding — do not claim anything "
            "beyond what those results confirm."})
        try:
            final = self.llm.chat(messages)
            summary = (final.content or "").strip() or "Reached tool-turn limit with no final summary."
        except Exception as e:
            summary = f"Reached tool-turn limit; summary call failed: {e}"
        if tool_results:
            summary += "\n[Tools executed]\n" + "\n".join(tool_results)
        return summary

    # ------------------------------------------------------------ comms
    def process_inter_agent_messages(self):
        """Processes inbox messages by actually executing matching tools."""
        messages = self.bus.read_inbox(mark_read=True)
        results = []
        for msg in messages:
            sender = msg.get("sender")
            action = msg.get("action", "")
            payload = msg.get("payload", {}) or {}
            if action.startswith("reply_"):
                # Replies are informational; record and move on.
                results.append(f"Received reply '{action}' from {sender}.")
                continue

            if self.tools and action in self.tools.tools:
                try:
                    result = self.tools.execute_tool(action, payload)
                    reply = {"status": "success", "result": str(result)[:1500]}
                except Exception as e:
                    reply = {"status": "error", "result": f"{action} failed: {e}"}
            else:
                reply = {"status": "unsupported",
                         "result": f"{self.name} has no tool named '{action}'. "
                                   f"Available: {sorted(self.tools.tools) if self.tools else []}"}
            self.bus.reply_message(msg, reply)
            self.record_experience(
                f"{sender} asked me to run '{action}'; status: {reply['status']}.",
                category="memory", confidence=0.55)
            results.append(f"Executed '{action}' from {sender}: {reply['status']}.")
        return results

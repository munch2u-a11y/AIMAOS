import os

def _find_aimaos_root():
    p = os.path.dirname(os.path.abspath(__file__))
    while p != os.path.dirname(p) and not os.path.exists(os.path.join(p, "aimaos_config.yaml")):
        p = os.path.dirname(p)
    return p
AIMAOS_ROOT = os.environ.get("AIMAOS_ROOT") or _find_aimaos_root()
import sys
import logging
import importlib.util

sys.path.insert(0, AIMAOS_ROOT)
from core.office_agent import OfficeAgent

logger = logging.getLogger(__name__)


def load_tool(name, filepath):
    spec = importlib.util.spec_from_file_location(f"finn_tool_{name}", filepath)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class FinnAgent(OfficeAgent):
    """Finn-AI: Security Officer, Direct Communicator & Comms Gateway.
    Helix-style mini-agent: ultra-minimal evolving-belief prompt, real LLM
    single-thought turns, and a private mRAG identity store.
    """
    def __init__(self, config=None):
        super().__init__("Finn", role="Security Officer & Comms Gateway", config=config)

    def process_user_message(self, message, sender="client@example.com", channel="web_ui"):
        """Single-thought turn: triages an incoming user message onto the
        Office Board, then answers the user with Finn's own (LLM) voice."""
        triage_mod = load_tool("triage_incoming", os.path.join(AIMAOS_ROOT, "Finn-AI/tools/triage_incoming.py"))
        triage_res = triage_mod.execute(sender_address=sender, message=message, channel=channel)
        self.record_experience(
            f"I triaged an incoming message from the {channel} channel.",
            category="memory", confidence=0.55)

        # Let Finn speak for himself when the model is reachable; fall back to
        # a plain acknowledgement when it is not.
        try:
            resp = self.llm.chat([
                {"role": "system", "content": self.get_system_prompt(message)},
                {"role": "user", "content":
                    f"An office visitor ({sender}, via {channel}) just sent: '{message}'.\n"
                    f"Your triage tool already logged it: {triage_res}\n"
                    "Reply to the visitor in 2-3 friendly professional sentences: "
                    "confirm what was logged, who will handle it, and what happens next."},
            ])
            voice = (resp.content or "").strip()
        except Exception as e:
            logger.warning(f"[Finn] LLM voice unavailable: {e}")
            voice = ""

        if not voice:
            voice = "Our office has logged your request and the assigned agent will take it up in priority order."

        return (f"Hello! I am **Finn**, AIMAOS Security Officer & Comms Gateway.\n\n"
                f"{voice}\n\n{triage_res}")

    def commandeer(self, calling_agent, recipient_email, subject, body, attachments=None):
        """Allows a peer agent to commandeer Finn's communication gateway."""
        cmd_mod = load_tool("commandeer_channel", os.path.join(AIMAOS_ROOT, "Finn-AI/tools/commandeer_channel.py"))
        result = cmd_mod.execute(calling_agent, recipient_email, subject, body, attachments)
        self.record_experience(
            f"{calling_agent} requested use of my communications gateway.",
            category="memory", confidence=0.55)
        return result

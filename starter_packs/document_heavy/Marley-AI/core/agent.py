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


def _load_orchestrator():
    path = os.path.join(AIMAOS_ROOT, "Marley-AI/core/orchestrator.py")
    spec = importlib.util.spec_from_file_location("marley_orchestrator_mod", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.MarleyOrchestrator


class MarleyAgent(OfficeAgent):
    """Marley-AI: Office Manager & Priority Scheduler.
    Helix-style mini-agent with the scheduling prerogative: Marley owns the
    dispatch order of every office turn (see core/office_daemon.py for the
    autonomous pulse loop Marley drives).
    """
    def __init__(self, config=None):
        super().__init__("Marley", role="Office Manager & Priority Scheduler", config=config)
        self.orchestrator = _load_orchestrator()()

    def dispatch_next_turn(self):
        """Marley's scheduling decision: which agent gets the next turn."""
        return self.orchestrator.dispatch_next_turn()

    def execute_single_turn(self, task_id=None):
        """Marley's own single turn is a scheduling turn: scan the board and
        dispatch. Tasks assigned *to Marley* (e.g. scheduling requests) fall
        through to the normal LLM task loop."""
        own_tasks = self.board.get_pending_tasks_for("Marley")
        if own_tasks:
            return super().execute_single_turn(task_id=task_id)

        turn = self.dispatch_next_turn()
        if isinstance(turn, dict):
            self.record_experience(
                f"I dispatched a {turn['priority']} priority task to {turn['assigned_agent']}.",
                category="memory", confidence=0.55)
        return {
            "system_prompt": self.get_system_prompt(),
            "model": self.model,
            "turn_dispatch": turn,
        }

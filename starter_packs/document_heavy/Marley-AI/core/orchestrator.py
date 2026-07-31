import os

def _find_aimaos_root():
    p = os.path.dirname(os.path.abspath(__file__))
    while p != os.path.dirname(p) and not os.path.exists(os.path.join(p, "aimaos_config.yaml")):
        p = os.path.dirname(p)
    return p
AIMAOS_ROOT = os.environ.get("AIMAOS_ROOT") or _find_aimaos_root()
import sys
import time
import logging
from datetime import datetime

sys.path.insert(0, AIMAOS_ROOT)
from core.comms.office_board import OfficeBoard

logger = logging.getLogger(__name__)

class MarleyOrchestrator:
    """
    Marley Office Manager & CPU/GPU Turn Dispatcher.
    Prevents hardware overload on local LLM setups by scheduling and prioritizing agent turns.
    """
    def __init__(self):
        self.board = OfficeBoard()

    def dispatch_next_turn(self):
        """
        Scans all pending tasks on the Office Board, enforces resource priority,
        and assigns execution turns.
        """
        # Fetch queued tasks sorted by priority. Tasks already dispatched
        # ("in_progress") must be excluded or the same task is re-dispatched
        # on every turn while queued work starves behind it.
        priority_order = {"CRITICAL": 0, "HIGH": 1, "NORMAL": 2, "BACKGROUND": 3}
        self.board.board = self.board._load_board()
        active_tasks = [t for t in self.board.board.get("active_tasks", []) if t.get("status") == "queued"]

        if not active_tasks:
            return "No queued tasks on the Office Board. Office is idle."

        # Sort tasks by priority
        sorted_tasks = sorted(active_tasks, key=lambda x: priority_order.get(x.get("priority", "NORMAL"), 99))
        top_task = sorted_tasks[0]

        target_agent = top_task["assigned_agent"]
        priority = top_task["priority"]
        task_id = top_task["id"]

        # If high priority task exists, deprioritize background maintenance
        if priority in ["CRITICAL", "HIGH"]:
            self.board.log_activity(f"[MARLEY DISPATCHER] High-Priority Task Detected ({top_task['title']}). Assigning turn to {target_agent}. Deprioritizing background maintenance.")
        else:
            self.board.log_activity(f"[MARLEY DISPATCHER] Assigning turn to {target_agent} for '{top_task['title']}'.")

        # Set task in progress
        self.board.update_task_status(task_id, "in_progress")
        self.board.update_agent_status(target_agent, "working")

        return {
            "task_id": task_id,
            "assigned_agent": target_agent,
            "priority": priority,
            "title": top_task["title"],
            "status": "in_progress"
        }

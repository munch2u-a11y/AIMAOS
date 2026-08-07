import os

def _find_aimaos_root():
    p = os.path.dirname(os.path.abspath(__file__))
    while p != os.path.dirname(p) and not os.path.exists(os.path.join(p, "aimaos_config.yaml")):
        p = os.path.dirname(p)
    return p
AIMAOS_ROOT = os.environ.get("AIMAOS_ROOT") or _find_aimaos_root()
import json
import logging
from datetime import datetime, timedelta
from core.atomic_io import atomic_write_json
from core.file_lock import exclusive_file_lock

logger = logging.getLogger(__name__)

OFFICE_BOARD_FILE = os.path.join(AIMAOS_ROOT, "comms/office_board.json")
OFFICE_BOARD_LOCK = OFFICE_BOARD_FILE + ".lock"

class OfficeBoard:
    """
    Central Bulletin Board & Activity Stream for AIMAOS.
    Tracks active tasks, priority queues, agent turn assignments, and live activity stream.

    Multiple agent processes read and mutate this board concurrently, so every
    mutation re-reads the file under an exclusive advisory lock before writing back —
    otherwise two agents holding stale in-memory copies overwrite each other's
    tasks (last-writer-wins data loss).
    """
    def __init__(self):
        os.makedirs(os.path.dirname(OFFICE_BOARD_FILE), exist_ok=True)
        self.board = self._load_board()

    def _default_board(self):
        return {
            "active_tasks": [],
            "completed_tasks": [],
            "activity_stream": [],
            "agent_statuses": {
                "Alix": "idle",
                "Kai": "idle",
                "Marley": "idle",
                "Quinn": "idle",
                "Zoe": "idle",
                "Finn": "idle",
                "Rae": "idle"
            }
        }

    def _load_board(self):
        if os.path.exists(OFFICE_BOARD_FILE):
            try:
                with open(OFFICE_BOARD_FILE, "r") as f:
                    return json.load(f)
            except Exception:
                pass
        return self._default_board()

    def _locked_mutation(self, mutate_fn):
        """Re-read, mutate and persist the compatibility board atomically.

        SQLite receives both active and completed state.  The JSON board is
        retained during the beta for compatibility with existing agents, but
        database sync failures are logged instead of silently hidden.
        """
        with exclusive_file_lock(OFFICE_BOARD_LOCK):
            self.board = self._load_board()
            result = mutate_fn(self.board)
            try:
                from core.security import load_security_config
                retention_days = max(
                    1, int(load_security_config().get("privacy", {}).get("log_retention_days", 30))
                )
                cutoff = datetime.now() - timedelta(days=retention_days)
                completed = []
                for task in self.board.get("completed_tasks", []):
                    try:
                        completed_at = datetime.fromisoformat(
                            task.get("completed_at") or task.get("updated_at") or task.get("created_at")
                        )
                    except (TypeError, ValueError):
                        completed_at = datetime.now()
                    if completed_at >= cutoff:
                        completed.append(task)
                self.board["completed_tasks"] = completed[-500:]
            except Exception as exc:
                logger.warning("Could not prune Office Board history: %s", exc)
            atomic_write_json(OFFICE_BOARD_FILE, self.board)
            try:
                from core.db.office_sqlite import OfficeSQLite
                db = OfficeSQLite()
                all_tasks = (self.board.get("active_tasks", [])
                             + self.board.get("completed_tasks", []))
                for t in all_tasks:
                    db.upsert_task(
                        task_id=t.get("id") or t.get("task_id"),
                        title=t.get("title", "Untitled"),
                        description=str(t.get("details", "")),
                        assigned_agent=t.get("assigned_agent", "Unassigned"),
                        priority=t.get("priority", "NORMAL"),
                        status=t.get("status", "queued")
                    )
            except Exception as exc:
                logger.exception("Could not synchronize Office Board to SQLite: %s", exc)
            return result

    def _append_activity(self, board, message):
        board["activity_stream"].append({
            "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "message": message
        })
        board["activity_stream"] = board["activity_stream"][-100:]

    def post_task(self, title, requester, target_agent, priority="HIGH", details=None):
        task_id = f"task_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
        task = {
            "id": task_id,
            "title": title,
            "requester": requester,
            "assigned_agent": target_agent,
            "priority": priority,
            "status": "queued",
            "details": details or {},
            "created_at": datetime.now().isoformat()
        }

        def mutate(board):
            board["active_tasks"].append(task)
            self._append_activity(board, f"[{requester}] Posted task '{title}' assigned to {target_agent} (Priority: {priority})")
            return task_id

        return self._locked_mutation(mutate)

    def log_activity(self, message):
        def mutate(board):
            self._append_activity(board, message)

        self._locked_mutation(mutate)

    def update_task_status(self, task_id, status, result=None):
        def mutate(board):
            for t in board["active_tasks"]:
                if t["id"] == task_id:
                    t["status"] = status
                    if result:
                        t["result"] = result
                    if status == "completed":
                        t["completed_at"] = datetime.now().isoformat()
                        board["active_tasks"].remove(t)
                        board["completed_tasks"].append(t)
                        self._append_activity(board, f"[{t['assigned_agent']}] Completed task '{t['title']}'")
                    elif status == "failed":
                        t["retries"] = int(t.get("retries", 0)) + 1
                        t["failed_at"] = datetime.now().isoformat()
                    elif status == "in_progress":
                        t["dispatched_at"] = datetime.now().isoformat()
                    return True
            return False

        return self._locked_mutation(mutate)

    def update_agent_status(self, agent_name, status):
        def mutate(board):
            board.setdefault("agent_statuses", {})[agent_name] = status

        self._locked_mutation(mutate)

    def get_pending_tasks_for(self, agent_name):
        # Include both freshly queued tasks and tasks Marley has already
        # dispatched ("in_progress") — otherwise dispatched tasks are invisible
        # to the assigned agent and strand on the board forever.
        priority_weights = {"CRITICAL": 0, "HIGH": 1, "NORMAL": 2, "BACKGROUND": 3}
        self.board = self._load_board()
        tasks = [t for t in self.board["active_tasks"]
                 if t["assigned_agent"] == agent_name and t["status"] in ("queued", "in_progress")]
        tasks.sort(key=lambda x: priority_weights.get(x["priority"], 99))
        return tasks

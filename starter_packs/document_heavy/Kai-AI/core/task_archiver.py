import os

def _find_aimaos_root():
    p = os.path.dirname(os.path.abspath(__file__))
    while p != os.path.dirname(p) and not os.path.exists(os.path.join(p, "aimaos_config.yaml")):
        p = os.path.dirname(p)
    return p
AIMAOS_ROOT = os.environ.get("AIMAOS_ROOT") or _find_aimaos_root()
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

TASK_LOGS_DIR = os.path.join(AIMAOS_ROOT, "comms/task_logs")

class KaiTaskArchiver:
    """
    Kai Task Log Archiver & Knowledge Cataloger for AIMAOS.
    Captures completed office task traces into permanent structured JSON archives for Zoe's report synthesis.
    """
    def __init__(self):
        os.makedirs(TASK_LOGS_DIR, exist_ok=True)

    def archive_task_execution(self, task_data, execution_trace):
        task_id = task_data.get("id", f"task_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        filepath = os.path.join(TASK_LOGS_DIR, f"{task_id}.json")

        archive_entry = {
            "task_id": task_id,
            "title": task_data.get("title"),
            "requester": task_data.get("requester"),
            "assigned_agent": task_data.get("assigned_agent"),
            "priority": task_data.get("priority"),
            "created_at": task_data.get("created_at"),
            "archived_at": datetime.now().isoformat(),
            "execution_trace": execution_trace,
            "status": "archived"
        }

        with open(filepath, "w") as f:
            json.dump(archive_entry, f, indent=2)

        logger.info(f"[KAI ARCHIVER] Archived task trace '{task_id}' to {filepath}")
        return filepath

    def get_all_archived_logs(self):
        logs = []
        if os.path.exists(TASK_LOGS_DIR):
            for f in os.listdir(TASK_LOGS_DIR):
                if f.endswith(".json"):
                    fpath = os.path.join(TASK_LOGS_DIR, f)
                    try:
                        with open(fpath, "r") as log_file:
                            logs.append(json.load(log_file))
                    except Exception:
                        pass
        return logs

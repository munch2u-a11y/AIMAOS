import os

def _find_aimaos_root():
    p = os.path.dirname(os.path.abspath(__file__))
    while p != os.path.dirname(p) and not os.path.exists(os.path.join(p, "aimaos_config.yaml")):
        p = os.path.dirname(p)
    return p
AIMAOS_ROOT = os.environ.get("AIMAOS_ROOT") or _find_aimaos_root()
import sys
import json

sys.path.insert(0, AIMAOS_ROOT)
from core.comms.office_board import OfficeBoard

TOOL_DEFINITION = {
    "name": "check_office_status",
    "description": "Queries the central Office Board for live agent statuses, pending/working tasks, and recent office activity stream feeds.",
    "parameters": {
        "type": "object",
        "properties": {}
    }
}

def execute():
    board = OfficeBoard()
    active = board.board.get("active_tasks", [])
    completed = board.board.get("completed_tasks", [])
    statuses = board.board.get("agent_statuses", {})
    stream = board.board.get("activity_stream", [])[-5:]

    summary = {
        "active_task_count": len(active),
        "completed_task_count": len(completed),
        "agent_statuses": statuses,
        "active_tasks": active,
        "recent_activity": stream
    }

    return json.dumps(summary, indent=2)

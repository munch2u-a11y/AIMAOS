import os

def _find_aimaos_root():
    p = os.path.dirname(os.path.abspath(__file__))
    while p != os.path.dirname(p) and not os.path.exists(os.path.join(p, "aimaos_config.yaml")):
        p = os.path.dirname(p)
    return p
AIMAOS_ROOT = os.environ.get("AIMAOS_ROOT") or _find_aimaos_root()
import json
from datetime import datetime

CALENDAR_FILE = os.path.join(AIMAOS_ROOT, "Marley-AI/workspace/calendar/events.json")

TOOL_DEFINITION = {
    "name": "manage_schedule",
    "description": "Schedules, updates, or lists calendar events, hearing dates, and filing deadlines for clients and peer agents.",
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["add_event", "list_events", "get_deadline"],
                "description": "Action to perform."
            },
            "event_title": {
                "type": "string",
                "description": "Title or summary of the event/deadline."
            },
            "date": {
                "type": "string",
                "description": "Date or timestamp for the event (e.g. '2026-08-15' or 'Tomorrow at 10:00 AM')."
            },
            "client_name": {
                "type": "string",
                "description": "Optional client associated with this schedule event."
            }
        },
        "required": ["action"]
    }
}

def _load_events():
    os.makedirs(os.path.dirname(CALENDAR_FILE), exist_ok=True)
    if os.path.exists(CALENDAR_FILE):
        try:
            with open(CALENDAR_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return []

def _save_events(events):
    os.makedirs(os.path.dirname(CALENDAR_FILE), exist_ok=True)
    with open(CALENDAR_FILE, "w") as f:
        json.dump(events, f, indent=2)

def execute(action, event_title=None, date=None, client_name=None):
    events = _load_events()

    if action == "add_event":
        if not event_title or not date:
            return "Error: event_title and date are required for add_event."
        entry = {
            "id": f"evt_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "title": event_title,
            "date": date,
            "client_name": client_name or "General",
            "created_at": datetime.now().isoformat()
        }
        events.append(entry)
        _save_events(events)
        return f"Successfully scheduled event '{event_title}' for {date} (Client: {client_name or 'General'})."

    elif action == "list_events":
        if not events:
            return "Calendar is empty. No scheduled events found."
        res = [f"Total Scheduled Events: {len(events)}"]
        for e in events:
            res.append(f"- [{e['date']}] {e['title']} (Client: {e.get('client_name', 'N/A')})")
        return "\n".join(res)

    else:
        return "Invalid schedule action."

import os

def _find_aimaos_root():
    p = os.path.dirname(os.path.abspath(__file__))
    while p != os.path.dirname(p) and not os.path.exists(os.path.join(p, "aimaos_config.yaml")):
        p = os.path.dirname(p)
    return p
AIMAOS_ROOT = os.environ.get("AIMAOS_ROOT") or _find_aimaos_root()
from core.local_calendar import LocalCalendar

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
            },
            "priority": {
                "type": "string",
                "enum": ["CRITICAL", "HIGH", "NORMAL", "BACKGROUND"],
                "description": "Operational priority for the local agenda."
            }
        },
        "required": ["action"]
    }
}

def execute(action, event_title=None, date=None, client_name=None, priority="NORMAL"):
    calendar = LocalCalendar()

    if action == "add_event":
        if not event_title or not date:
            return "Error: event_title and date are required for add_event."
        key = f"manual:{client_name or 'General'}:{event_title}:{date}".casefold()
        _event, created = calendar.upsert_event(
            event_key=key,
            title=event_title,
            date=date,
            client_name=client_name,
            priority=priority,
            kind="calendar_event",
        )
        verb = "Scheduled" if created else "Refreshed"
        return f"{verb} event '{event_title}' for {date} (Client: {client_name or 'General'})."

    elif action == "list_events":
        events = calendar.list_events()
        if not events:
            return "Calendar is empty. No scheduled events found."
        res = [f"Total Scheduled Events: {len(events)}"]
        for e in events:
            res.append(f"- [{e['date']}] {e['title']} (Client: {e.get('client_name', 'N/A')})")
        return "\n".join(res)

    elif action == "get_deadline":
        events = calendar.list_events()
        if client_name:
            events = [event for event in events
                      if str(event.get("client_name", "")).casefold() == client_name.casefold()]
        if not events:
            return f"No open deadlines found for {client_name or 'the office'}."
        event = events[0]
        return f"Next deadline: [{event['date']}] {event['title']} (Client: {event.get('client_name', 'N/A')})"

    return "Invalid schedule action."

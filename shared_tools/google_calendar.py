"""Google Calendar integration, shared by every AIMAOS agent.

Talks to the Calendar v3 REST API directly over `requests` — no
google-api-python-client / google-auth dependency needed (this box installs
packages offline, so keeping the dependency surface to what's already
vendored matters). The office only needs to supply a valid OAuth2 access
token; see shared_tools/README.md for how to obtain one.

Env vars:
  GOOGLE_CALENDAR_ACCESS_TOKEN  required — OAuth2 bearer token with at least
                                the https://www.googleapis.com/auth/calendar
                                (or .events) scope. Access tokens expire
                                (typically 1h); the user is responsible for
                                keeping this env var refreshed, e.g. via a
                                small cron script calling their OAuth
                                refresh token — that flow is intentionally
                                out of scope for this tool.
  GOOGLE_CALENDAR_ID            optional — defaults to "primary".
"""
import os
from datetime import datetime, timedelta

import requests

API_BASE = "https://www.googleapis.com/calendar/v3"
REQUEST_TIMEOUT = 15

TOOL_DEFINITION = {
    "name": "google_calendar",
    "description": "Lists, creates, updates, or deletes events on the connected Google Calendar. "
                   "Requires the office's Google account to be connected (GOOGLE_CALENDAR_ACCESS_TOKEN).",
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["list_events", "create_event", "update_event", "delete_event"],
                "description": "Which calendar operation to perform."
            },
            "summary": {
                "type": "string",
                "description": "Event title. Required for create_event; optional for update_event."
            },
            "description": {
                "type": "string",
                "description": "Event details/notes (optional)."
            },
            "start_datetime": {
                "type": "string",
                "description": "ISO 8601 start time, e.g. '2026-08-15T10:00:00-04:00'. Required for create_event."
            },
            "end_datetime": {
                "type": "string",
                "description": "ISO 8601 end time. If omitted on create_event, defaults to start + 1 hour."
            },
            "timezone": {
                "type": "string",
                "description": "IANA timezone name (e.g. 'America/New_York'), used if start/end datetimes "
                               "don't carry a UTC offset."
            },
            "attendees": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Attendee email addresses to invite (optional)."
            },
            "event_id": {
                "type": "string",
                "description": "Existing event id. Required for update_event and delete_event."
            },
            "time_min": {
                "type": "string",
                "description": "list_events only: ISO 8601 lower bound (default: now)."
            },
            "time_max": {
                "type": "string",
                "description": "list_events only: ISO 8601 upper bound (default: 30 days from time_min)."
            },
            "max_results": {
                "type": "integer",
                "description": "list_events only: max events to return (default 10)."
            }
        },
        "required": ["action"]
    }
}

_NOT_CONNECTED = (
    "Google Calendar isn't connected yet. Set the GOOGLE_CALENDAR_ACCESS_TOKEN environment "
    "variable to a valid OAuth2 access token with calendar scope (optionally GOOGLE_CALENDAR_ID "
    "for a non-primary calendar). See shared_tools/README.md for the setup steps."
)


def _headers():
    token = os.environ.get("GOOGLE_CALENDAR_ACCESS_TOKEN")
    if not token:
        return None
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _calendar_id():
    return os.environ.get("GOOGLE_CALENDAR_ID", "primary")


def _request(method, path, headers, **kwargs):
    url = f"{API_BASE}/{path}"
    try:
        resp = requests.request(method, url, headers=headers, timeout=REQUEST_TIMEOUT, **kwargs)
    except requests.exceptions.RequestException as e:
        return None, f"Google Calendar request failed (network error): {e}"
    if resp.status_code == 401:
        return None, "Google Calendar rejected the access token (expired or invalid); refresh GOOGLE_CALENDAR_ACCESS_TOKEN."
    if not resp.ok:
        return None, f"Google Calendar API error {resp.status_code}: {resp.text[:400]}"
    return (resp.json() if resp.content else {}), None


def _event_time(dt_str, timezone):
    body = {"dateTime": dt_str}
    if timezone:
        body["timeZone"] = timezone
    return body


def execute(action, summary=None, description=None, start_datetime=None, end_datetime=None,
            timezone=None, attendees=None, event_id=None, time_min=None, time_max=None,
            max_results=10):
    headers = _headers()
    if headers is None:
        return _NOT_CONNECTED
    cal_id = _calendar_id()

    if action == "list_events":
        params = {
            "singleEvents": "true",
            "orderBy": "startTime",
            "maxResults": max(1, min(int(max_results or 10), 50)),
            "timeMin": time_min or datetime.utcnow().isoformat() + "Z",
        }
        if time_max:
            params["timeMax"] = time_max
        data, err = _request("GET", f"calendars/{cal_id}/events", headers, params=params)
        if err:
            return err
        items = data.get("items", [])
        if not items:
            return "No events found in the requested window."
        lines = []
        for ev in items:
            start = ev.get("start", {}).get("dateTime") or ev.get("start", {}).get("date")
            lines.append(f"- {ev.get('summary', '(untitled)')} @ {start} (id: {ev.get('id')})")
        return f"{len(items)} event(s):\n" + "\n".join(lines)

    if action == "create_event":
        if not summary or not start_datetime:
            return "Error: create_event requires summary and start_datetime."
        if not end_datetime:
            try:
                start_dt = datetime.fromisoformat(start_datetime)
                end_datetime = (start_dt + timedelta(hours=1)).isoformat()
            except ValueError:
                return "Error: start_datetime must be ISO 8601 (e.g. 2026-08-15T10:00:00-04:00)."
        body = {
            "summary": summary,
            "start": _event_time(start_datetime, timezone),
            "end": _event_time(end_datetime, timezone),
        }
        if description:
            body["description"] = description
        if attendees:
            body["attendees"] = [{"email": a} for a in attendees]
        data, err = _request("POST", f"calendars/{cal_id}/events", headers, json=body)
        if err:
            return err
        return f"Created event '{data.get('summary')}' (id: {data.get('id')}): {data.get('htmlLink')}"

    if action == "update_event":
        if not event_id:
            return "Error: update_event requires event_id."
        body = {}
        if summary:
            body["summary"] = summary
        if description:
            body["description"] = description
        if start_datetime:
            body["start"] = _event_time(start_datetime, timezone)
        if end_datetime:
            body["end"] = _event_time(end_datetime, timezone)
        if attendees:
            body["attendees"] = [{"email": a} for a in attendees]
        if not body:
            return "Error: update_event needs at least one field to change."
        data, err = _request("PATCH", f"calendars/{cal_id}/events/{event_id}", headers, json=body)
        if err:
            return err
        return f"Updated event '{data.get('summary')}' (id: {data.get('id')})."

    if action == "delete_event":
        if not event_id:
            return "Error: delete_event requires event_id."
        _, err = _request("DELETE", f"calendars/{cal_id}/events/{event_id}", headers)
        if err:
            return err
        return f"Deleted event {event_id}."

    return f"Unknown action '{action}'. Use list_events, create_event, update_event, or delete_event."

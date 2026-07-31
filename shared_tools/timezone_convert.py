"""Timezone conversion, shared by every AIMAOS agent. Pure stdlib (zoneinfo),
no credentials — useful for scheduling hearings/calls across timezones.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

TOOL_DEFINITION = {
    "name": "timezone_convert",
    "description": "Converts a datetime from one IANA timezone to another (e.g. 'America/New_York' to "
                   "'America/Los_Angeles'). Pass 'now' as datetime_str for the current time.",
    "parameters": {
        "type": "object",
        "properties": {
            "datetime_str": {
                "type": "string",
                "description": "ISO 8601 datetime (e.g. '2026-08-15T14:00:00') interpreted in from_tz, "
                               "or the literal 'now'."
            },
            "from_tz": {
                "type": "string",
                "description": "Source IANA timezone name, e.g. 'America/New_York'."
            },
            "to_tz": {
                "type": "string",
                "description": "Target IANA timezone name, e.g. 'Europe/London'."
            }
        },
        "required": ["datetime_str", "from_tz", "to_tz"]
    }
}


def execute(datetime_str, from_tz, to_tz):
    try:
        source_zone = ZoneInfo(from_tz)
    except Exception:
        return f"Error: unknown from_tz '{from_tz}'. Use an IANA name, e.g. 'America/New_York'."
    try:
        target_zone = ZoneInfo(to_tz)
    except Exception:
        return f"Error: unknown to_tz '{to_tz}'. Use an IANA name, e.g. 'Europe/London'."

    if datetime_str.strip().lower() == "now":
        dt = datetime.now(source_zone)
    else:
        try:
            dt = datetime.fromisoformat(datetime_str)
        except ValueError:
            return f"Error: datetime_str must be ISO 8601 (e.g. '2026-08-15T14:00:00'), got '{datetime_str}'."
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=source_zone)
        else:
            dt = dt.astimezone(source_zone)

    converted = dt.astimezone(target_zone)
    return (f"{dt.strftime('%Y-%m-%d %H:%M:%S %Z')} ({from_tz}) = "
           f"{converted.strftime('%Y-%m-%d %H:%M:%S %Z')} ({to_tz})")

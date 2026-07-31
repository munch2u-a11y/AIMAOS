"""Internal calendar / scheduler for the tool pipeline.

An owned alternative to an external calendar service: one-time reminders
and cron-style recurring jobs, kept in a JSON file the agent maintains
itself. No background threads and no timers — the harness polls
`ScheduleStore.due()` (or a subagent calls the `due_reminders` tool) each
turn, receives whatever came due since the last check, and injects it
into the main context like any other input. Due items are informational
tool returns, so the runner ingests them into Layer 1 memory: a fired
reminder stays retrievable forever even after it leaves the window.

Recurrence is a standard 5-field cron subset (minute hour day month
weekday; supports * , - / lists), plus convenience keywords (daily,
weekdays, weekly, monthly, yearly) that derive their cron line from the
anchor time.

Times are given as "YYYY-MM-DD HH:MM", "YYYY-MM-DD" (09:00 assumed), or
"HH:MM" (today, or tomorrow when already past).
"""

import json
import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from mrag.adapters.tool_groups import Tool, ToolGroup

logger = logging.getLogger("mrag.adapters.scheduler")

REPEAT_KEYWORDS = {"daily", "weekdays", "weekly", "monthly", "yearly"}


def _parse_when(text: str, now: Optional[datetime] = None) -> Optional[datetime]:
    text = (text or "").strip()
    now = now or datetime.now()
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            pass
    try:
        day = datetime.strptime(text, "%Y-%m-%d")
        return day.replace(hour=9, minute=0)
    except ValueError:
        pass
    try:
        clock = datetime.strptime(text, "%H:%M")
        candidate = now.replace(hour=clock.hour, minute=clock.minute,
                                second=0, microsecond=0)
        return candidate if candidate > now else candidate + timedelta(days=1)
    except ValueError:
        return None


# --- cron subset -----------------------------------------------------------

def _parse_cron_field(field: str, low: int, high: int) -> Optional[set]:
    values = set()
    for part in field.split(","):
        part = part.strip()
        step = 1
        if "/" in part:
            part, step_text = part.split("/", 1)
            if not step_text.isdigit() or int(step_text) < 1:
                return None
            step = int(step_text)
        if part in ("*", ""):
            start, end = low, high
        elif "-" in part:
            bounds = part.split("-", 1)
            if not (bounds[0].isdigit() and bounds[1].isdigit()):
                return None
            start, end = int(bounds[0]), int(bounds[1])
        elif part.isdigit():
            start = end = int(part)
        else:
            return None
        if start < low or end > high or start > end:
            return None
        values.update(range(start, end + 1, step))
    return values


def parse_cron(spec: str) -> Optional[Dict[str, set]]:
    """5-field cron: minute hour day-of-month month day-of-week (0=Mon
    per Python's weekday(); 7 also accepted as Sunday)."""
    fields = spec.split()
    if len(fields) != 5:
        return None
    bounds = [(0, 59), (0, 23), (1, 31), (1, 12), (0, 7)]
    names = ["minute", "hour", "day", "month", "weekday"]
    parsed = {}
    for name, field, (low, high) in zip(names, fields, bounds):
        values = _parse_cron_field(field, low, high)
        if values is None:
            return None
        parsed[name] = values
    if 7 in parsed["weekday"]:  # 7 == Sunday == 6 in weekday()
        parsed["weekday"].discard(7)
        parsed["weekday"].add(6)
    return parsed


def _cron_matches(cron: Dict[str, set], moment: datetime) -> bool:
    return (moment.minute in cron["minute"]
            and moment.hour in cron["hour"]
            and moment.day in cron["day"]
            and moment.month in cron["month"]
            and moment.weekday() in cron["weekday"])


def next_occurrence(cron: Dict[str, set], after: datetime,
                    horizon_days: int = 400) -> Optional[datetime]:
    """First matching minute strictly after `after`. Scans day-by-day,
    then only matching hours/minutes, so a 400-day horizon stays cheap."""
    moment = (after + timedelta(minutes=1)).replace(second=0, microsecond=0)
    for _ in range(horizon_days + 1):
        if (moment.day in cron["day"] and moment.month in cron["month"]
                and moment.weekday() in cron["weekday"]):
            for hour in sorted(cron["hour"]):
                if hour < moment.hour:
                    continue
                for minute in sorted(cron["minute"]):
                    if hour == moment.hour and minute < moment.minute:
                        continue
                    return moment.replace(hour=hour, minute=minute)
        moment = (moment + timedelta(days=1)).replace(hour=0, minute=0)
    return None


def _keyword_to_cron(keyword: str, anchor: datetime) -> str:
    minute, hour = anchor.minute, anchor.hour
    if keyword == "daily":
        return f"{minute} {hour} * * *"
    if keyword == "weekdays":
        return f"{minute} {hour} * * 0-4"
    if keyword == "weekly":
        return f"{minute} {hour} * * {anchor.weekday()}"
    if keyword == "monthly":
        return f"{minute} {hour} {anchor.day} * *"
    return f"{minute} {hour} {anchor.day} {anchor.month} *"  # yearly


# --- store -------------------------------------------------------------------

class ScheduleStore:
    """JSON-backed schedule. Poll `due()` from the harness each turn (or
    via the due_reminders tool) — that call is the scheduler's heartbeat;
    there are no threads or timers."""

    def __init__(self, path: Optional[str] = None):
        self.path = path or os.environ.get(
            "MRAG_SCHEDULE_PATH") or os.path.expanduser("~/.mrag_schedule.json")

    def _load(self) -> Dict[str, Any]:
        try:
            with open(self.path) as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return {"next_id": 1, "entries": []}

    def _save(self, data: Dict[str, Any]):
        with open(self.path, "w") as f:
            json.dump(data, f, indent=1)

    def add(self, text: str, when: str, repeat: str = "") -> str:
        text = (text or "").strip()
        if not text:
            return "ERROR: reminder text is required."
        repeat = (repeat or "").strip().lower()
        anchor = _parse_when(when)
        if anchor is None and not repeat:
            return (f"ERROR: could not parse when='{when}'. Use 'YYYY-MM-DD HH:MM', "
                    f"'YYYY-MM-DD', or 'HH:MM'.")

        cron_line = ""
        if repeat:
            if repeat in REPEAT_KEYWORDS:
                if anchor is None:
                    return (f"ERROR: repeat='{repeat}' needs a parseable anchor time "
                            f"(got when='{when}').")
                cron_line = _keyword_to_cron(repeat, anchor)
            elif parse_cron(repeat):
                cron_line = repeat
            else:
                return (f"ERROR: repeat='{repeat}' is neither a keyword "
                        f"({', '.join(sorted(REPEAT_KEYWORDS))}) nor a valid "
                        f"5-field cron line ('min hour day month weekday', 0=Monday).")

        data = self._load()
        entry_id = f"s{data['next_id']}"
        data["next_id"] += 1
        entry = {"id": entry_id, "text": text, "fired": False}
        if cron_line:
            entry["cron"] = cron_line
            start = anchor or datetime.now()
            entry["last_fired"] = (start - timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M")
        else:
            entry["when"] = anchor.strftime("%Y-%m-%d %H:%M")
        data["entries"].append(entry)
        self._save(data)
        if cron_line:
            upcoming = next_occurrence(parse_cron(cron_line),
                                       datetime.now() - timedelta(minutes=1))
            first = upcoming.strftime("%Y-%m-%d %H:%M") if upcoming else "unknown"
            return f"ok, scheduled {entry_id} (recurring '{cron_line}', next: {first}): {text}"
        return f"ok, scheduled {entry_id} for {entry['when']}: {text}"

    def upcoming(self, days: int = 7, now: Optional[datetime] = None) -> str:
        now = now or datetime.now()
        horizon = now + timedelta(days=int(days))
        occurrences: List[Tuple[datetime, str, str]] = []
        for entry in self._load()["entries"]:
            if "cron" in entry:
                cron = parse_cron(entry["cron"])
                moment = now
                while True:
                    moment = next_occurrence(cron, moment)
                    if moment is None or moment > horizon:
                        break
                    occurrences.append(
                        (moment, entry["id"], f"{entry['text']} (recurring '{entry['cron']}')"))
                    if len([o for o in occurrences if o[1] == entry["id"]]) >= 10:
                        break
            elif not entry.get("fired"):
                when = datetime.strptime(entry["when"], "%Y-%m-%d %H:%M")
                if now <= when <= horizon:
                    occurrences.append((when, entry["id"], entry["text"]))
        occurrences.sort()
        if not occurrences:
            return f"Nothing scheduled in the next {days} day(s)."
        return "\n".join(
            f"{moment.strftime('%Y-%m-%d %H:%M')} [{entry_id}] {text}"
            for moment, entry_id, text in occurrences)

    def due(self, now: Optional[datetime] = None) -> str:
        """Everything that came due since the last check. One-time entries
        fire once (marked fired); recurring entries advance last_fired.
        This is the heartbeat — call it every turn from the harness."""
        now = now or datetime.now()
        data = self._load()
        due_lines: List[str] = []
        for entry in data["entries"]:
            if "cron" in entry:
                cron = parse_cron(entry["cron"])
                last = datetime.strptime(entry["last_fired"], "%Y-%m-%d %H:%M")
                fired_any = None
                moment = last
                while True:
                    moment = next_occurrence(cron, moment)
                    if moment is None or moment > now:
                        break
                    fired_any = moment
                if fired_any:
                    due_lines.append(
                        f"[{entry['id']}] DUE {fired_any.strftime('%Y-%m-%d %H:%M')}: {entry['text']}")
                    entry["last_fired"] = fired_any.strftime("%Y-%m-%d %H:%M")
            elif not entry.get("fired"):
                when = datetime.strptime(entry["when"], "%Y-%m-%d %H:%M")
                if when <= now:
                    due_lines.append(
                        f"[{entry['id']}] DUE {entry['when']}: {entry['text']}")
                    entry["fired"] = True
        # Fired one-time entries are kept (fired=True) for the record;
        # Layer 1 holds the durable copy once the return is ingested.
        self._save(data)
        return "\n".join(due_lines) if due_lines else "Nothing due."

    def cancel(self, entry_id: str) -> str:
        data = self._load()
        before = len(data["entries"])
        data["entries"] = [e for e in data["entries"] if e["id"] != str(entry_id)]
        if len(data["entries"]) == before:
            return f"ERROR: no entry {entry_id}."
        self._save(data)
        return f"ok, cancelled {entry_id}"


def build_schedule_group(store: Optional[ScheduleStore] = None) -> ToolGroup:
    store = store or ScheduleStore()
    return ToolGroup(
        name="schedule",
        summary="internal calendar: reminders, recurring cron-style jobs, upcoming events",
        tools=[
            Tool("add_event",
                 "Schedule a reminder or recurring job on the internal calendar.",
                 handler=store.add,
                 parameters={
                     "text": "string, what to be reminded of / the job",
                     "when": "string: 'YYYY-MM-DD HH:MM', 'YYYY-MM-DD', or 'HH:MM'",
                     "repeat": ("string, optional: daily | weekdays | weekly | monthly | "
                                "yearly, or a 5-field cron line 'min hour day month weekday' (0=Monday)"),
                 },
                 informational=False),
            Tool("list_schedule", "Upcoming events within a horizon, expanded and sorted.",
                 handler=store.upcoming, parameters={"days": "int, default 7"}),
            Tool("due_reminders",
                 "Everything due since the last check; fires one-time entries and advances recurring ones.",
                 handler=store.due, parameters={}),
            Tool("cancel_entry", "Cancel an entry by id.", handler=store.cancel,
                 parameters={"entry_id": "string, e.g. 's3'"},
                 informational=False),
        ],
    )

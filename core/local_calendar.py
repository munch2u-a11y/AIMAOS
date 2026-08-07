"""Private, idempotent local calendar used by Marley and the workstation."""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
from datetime import datetime

from core.atomic_io import atomic_write_json


def _find_aimaos_root() -> str:
    path = os.path.dirname(os.path.abspath(__file__))
    while path != os.path.dirname(path):
        if os.path.exists(os.path.join(path, "aimaos_config.yaml")):
            return path
        path = os.path.dirname(path)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


AIMAOS_ROOT = os.environ.get("AIMAOS_ROOT") or _find_aimaos_root()
DEFAULT_CALENDAR_PATH = os.path.join(AIMAOS_ROOT, "Marley-AI", "workspace", "calendar", "events.json")


def _clean_text(value, *, limit: int, fallback: str = "") -> str:
    text = " ".join(str(value or "").replace("\x00", "").split()).strip()
    return text[:limit] or fallback


class LocalCalendar:
    """A small crash-safe calendar with stable keys for recurring reviews."""

    def __init__(self, path: str = DEFAULT_CALENDAR_PATH):
        self.path = os.path.abspath(path)
        self.lock_path = self.path + ".lock"
        os.makedirs(os.path.dirname(self.path), exist_ok=True)

    def _load_unlocked(self) -> list[dict]:
        if not os.path.exists(self.path):
            return []
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
            return payload if isinstance(payload, list) else []
        except (OSError, json.JSONDecodeError):
            return []

    def _mutate(self, callback):
        with open(self.lock_path, "a+", encoding="utf-8") as lock_handle:
            fcntl.flock(lock_handle, fcntl.LOCK_EX)
            try:
                events = self._load_unlocked()
                result = callback(events)
                atomic_write_json(self.path, events)
                return result
            finally:
                fcntl.flock(lock_handle, fcntl.LOCK_UN)

    def list_events(self, *, include_completed: bool = False) -> list[dict]:
        events = self._load_unlocked()
        if not include_completed:
            events = [event for event in events if event.get("status", "open") != "completed"]
        return sorted(events, key=lambda event: (str(event.get("date", "9999")), event.get("title", "")))

    def upsert_event(
        self,
        *,
        event_key: str,
        title: str,
        date: str,
        client_name: str | None = None,
        priority: str = "NORMAL",
        kind: str = "event",
        source_task_id: str | None = None,
        blocker: str | None = None,
        next_action: str | None = None,
        audit_reason: str | None = None,
        self_repair_status: str | None = None,
    ) -> tuple[dict, bool]:
        key = _clean_text(event_key, limit=240)
        if not key:
            raise ValueError("event_key is required")
        title = _clean_text(title, limit=200)
        date = _clean_text(date, limit=80)
        if not title or not date:
            raise ValueError("title and date are required")
        now = datetime.now().isoformat()

        def mutate(events):
            existing = next((event for event in events if event.get("event_key") == key), None)
            created = existing is None
            if existing is None:
                digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
                existing = {
                    "id": f"evt_{digest}",
                    "event_key": key,
                    "created_at": now,
                    "status": "open",
                }
                events.append(existing)
            # Upserting an active reminder intentionally reopens it. This makes
            # a recurring manager review recover from a previously completed
            # calendar event without creating duplicate rows.
            existing["status"] = "open"
            existing.pop("completed_at", None)
            existing.update({
                "title": title,
                "date": date,
                "client_name": _clean_text(client_name, limit=120, fallback="General"),
                "priority": priority if priority in {"CRITICAL", "HIGH", "NORMAL", "BACKGROUND"} else "NORMAL",
                "kind": _clean_text(kind, limit=60, fallback="event"),
                "source_task_id": source_task_id,
                "blocker": _clean_text(blocker, limit=500),
                "next_action": _clean_text(next_action, limit=500),
                "audit_reason": _clean_text(audit_reason, limit=500),
                "self_repair_status": _clean_text(self_repair_status, limit=500),
                "updated_at": now,
            })
            return dict(existing), created

        return self._mutate(mutate)

    def complete_for_task(self, task_id: str) -> int:
        now = datetime.now().isoformat()

        def mutate(events):
            changed = 0
            for event in events:
                if event.get("source_task_id") == task_id and event.get("status", "open") != "completed":
                    event["status"] = "completed"
                    event["completed_at"] = now
                    event["updated_at"] = now
                    changed += 1
            return changed

        return self._mutate(mutate)

    def snooze_for_task(self, task_id: str, due_date: str) -> int:
        due_date = _clean_text(due_date, limit=80)
        now = datetime.now().isoformat()

        def mutate(events):
            changed = 0
            for event in events:
                if event.get("source_task_id") == task_id and event.get("status", "open") != "completed":
                    event["date"] = due_date
                    event["updated_at"] = now
                    changed += 1
            return changed

        return self._mutate(mutate)

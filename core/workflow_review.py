"""Deterministic daily workflow review for Marley's local workstation.

The review never sends messages or asks an LLM to invent work. It turns
communication requests into human follow-ups, evaluates explicit task
dependencies, flags misleading/failed completions for manager review, and
keeps Marley's private calendar synchronized without creating duplicates.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
from datetime import date, datetime, timedelta

from core.atomic_io import atomic_write_json
from core.agent_widgets import validate_widget_schema
from core.comms.office_board import OfficeBoard
from core.db.office_sqlite import OfficeSQLite
from core.local_calendar import LocalCalendar
from core.security import load_security_config, normalize_slug, path_is_sensitive, resolve_within


def _find_aimaos_root() -> str:
    path = os.path.dirname(os.path.abspath(__file__))
    while path != os.path.dirname(path):
        if os.path.exists(os.path.join(path, "aimaos_config.yaml")):
            return path
        path = os.path.dirname(path)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


AIMAOS_ROOT = os.environ.get("AIMAOS_ROOT") or _find_aimaos_root()
DEFAULT_STATE_PATH = os.path.join(AIMAOS_ROOT, "Marley-AI", "workspace", "workflow_review.json")
PRIORITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "NORMAL": 2, "BACKGROUND": 3}
FAILURE_MARKERS = (
    "unconfirmed/failed", "cannot be completed", "could not be completed",
    "no artifact", "security policy restrictions", "still outstanding",
)
COMMUNICATION_PATTERN = re.compile(r"\b(send|email|e-mail|contact|notify|call|update)\b", re.IGNORECASE)


def _clean(value, limit=500) -> str:
    return " ".join(str(value or "").replace("\x00", "").split()).strip()[:limit]


def _task_details(task: dict) -> dict:
    details = task.get("details")
    if not isinstance(details, dict):
        details = {}
        task["details"] = details
    return details


def _review_key(prefix: str, value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()[:20]
    return f"{prefix}:{digest}"


def _is_communication_task(task: dict) -> bool:
    details = _task_details(task)
    if details.get("work_type") == "human_follow_up":
        return False
    title = str(task.get("title", ""))
    return bool(
        details.get("draft_message")
        or (task.get("assigned_agent") == "Finn" and COMMUNICATION_PATTERN.search(title))
        or title.lower().startswith(("send ", "email ", "notify ", "contact ", "call "))
    )


def _communication_title(task: dict) -> str:
    details = _task_details(task)
    client = _clean(details.get("client_name"), 120) or "client"
    title = str(task.get("title", ""))
    action = "update" if "update" in title.lower() else "contact"
    return f"Attorney follow-up: {action} {client}"


def _result_needs_review(task: dict) -> bool:
    if task.get("status") != "completed":
        return False
    result = str(task.get("result") or "").lower()
    return any(marker in result for marker in FAILURE_MARKERS)


def _parse_created(task: dict, fallback: datetime) -> datetime:
    try:
        return datetime.fromisoformat(str(task.get("created_at")))
    except (TypeError, ValueError):
        return fallback


def _daily_state(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            value = json.load(handle)
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def run_daily_advancement_review(
    *,
    force: bool = False,
    now: datetime | None = None,
    board: OfficeBoard | None = None,
    calendar: LocalCalendar | None = None,
    state_path: str = DEFAULT_STATE_PATH,
    config: dict | None = None,
) -> dict:
    """Run at most once per local day unless forced; return a count-only report."""
    now = now or datetime.now()
    today = now.date().isoformat()
    cfg = config or load_security_config()
    workflow_cfg = cfg.get("workflow", {})
    if not workflow_cfg.get("daily_review_enabled", True):
        return {"ran": False, "reason": "disabled"}
    os.makedirs(os.path.dirname(state_path), exist_ok=True)
    lock_path = state_path + ".lock"
    with open(lock_path, "a+", encoding="utf-8") as state_lock:
        fcntl.flock(state_lock, fcntl.LOCK_EX)
        try:
            prior_state = _daily_state(state_path)
            if not force and prior_state.get("last_review_date") == today:
                return {
                    "ran": False,
                    "reason": "already_reviewed",
                    "last_report": prior_state.get("last_report", {}),
                }

            board = board or OfficeBoard()
            calendar = calendar or LocalCalendar()
            stale_hours = max(1, int(workflow_cfg.get("stale_task_hours", 24)))
            direct_communications = bool(workflow_cfg.get("direct_communications", False))
            report = {
                "ran": True,
                "communications_held": 0,
                "dependency_blocked": 0,
                "dependency_released": 0,
                "completion_reviews": 0,
                "stale_promoted": 0,
                "calendar_upserts": 0,
            }
            calendar_requests = []

            def mutate(payload):
                active = payload.setdefault("active_tasks", [])
                completed = payload.setdefault("completed_tasks", [])
                all_tasks = active + completed
                by_id = {str(task.get("id") or task.get("task_id")): task for task in all_tasks}
                completed_ids = {
                    task_id for task_id, task in by_id.items() if task.get("status") == "completed"
                }

                def unresolved_dependencies(task, trail=None):
                    trail = set(trail or ())
                    task_id = str(task.get("id") or task.get("task_id"))
                    if task_id in trail:
                        return [f"dependency cycle at {task_id}"]
                    trail.add(task_id)
                    details = _task_details(task)
                    dependencies = details.get("blocked_by") or details.get("depends_on") or []
                    if isinstance(dependencies, str):
                        dependencies = [dependencies]
                    unresolved = []
                    for dependency_id in dependencies[:30]:
                        dependency_id = str(dependency_id)
                        if dependency_id in completed_ids:
                            continue
                        dependency = by_id.get(dependency_id)
                        if dependency is None:
                            unresolved.append(f"unknown prerequisite {dependency_id}")
                            continue
                        nested = unresolved_dependencies(dependency, trail.copy())
                        unresolved.append(_clean(dependency.get("title"), 120) or dependency_id)
                        unresolved.extend(nested)
                    return list(dict.fromkeys(unresolved))

                existing_review_keys = {
                    _task_details(task).get("review_key") for task in all_tasks
                    if _task_details(task).get("review_key")
                }
                for task in active:
                    details = _task_details(task)
                    task_id = str(task.get("id") or task.get("task_id"))
                    if (task.get("status") == "waiting_on_human"
                            and details.get("requires_human")
                            and details.get("review_key")):
                        calendar_requests.append({
                            "event_key": details["review_key"],
                            "title": _clean(task.get("title"), 200),
                            "date": details.get("due_date") or today,
                            "client_name": _clean(details.get("client_name"), 120) or "General",
                            "priority": task.get("priority", "HIGH"),
                            "kind": details.get("work_type", "human_follow_up"),
                            "source_task_id": task_id,
                            "blocker": details.get("blocker"),
                            "next_action": details.get("next_action"),
                        })
                        continue
                    if (task.get("status") in {"queued", "failed"}
                            and _is_communication_task(task) and not direct_communications):
                        original_title = _clean(task.get("title"), 200)
                        client = _clean(details.get("client_name"), 120) or "General"
                        details.update({
                            "original_title": details.get("original_title") or original_title,
                            "work_type": "human_follow_up",
                            "requires_human": True,
                            "owner": "Attorney",
                            "due_date": details.get("due_date") or today,
                            "blocker": "Client communication requires attorney review and an approved channel.",
                            "next_action": f"Review the matter, update {client} outside AIMAOS, and record the outcome.",
                            "review_key": details.get("review_key") or f"communication:{task_id}",
                        })
                        task["title"] = _communication_title(task)
                        task["assigned_agent"] = "Attorney"
                        task["status"] = "waiting_on_human"
                        if PRIORITY_ORDER.get(task.get("priority", "NORMAL"), 2) > PRIORITY_ORDER["HIGH"]:
                            task["priority"] = "HIGH"
                        report["communications_held"] += 1
                        calendar_requests.append({
                            "event_key": details["review_key"],
                            "title": task["title"],
                            "date": details["due_date"],
                            "client_name": client,
                            "priority": task["priority"],
                            "kind": "human_follow_up",
                            "source_task_id": task_id,
                            "blocker": details["blocker"],
                            "next_action": details["next_action"],
                        })
                        continue

                    unresolved = unresolved_dependencies(task)
                    if unresolved and task.get("status") in {"queued", "blocked"}:
                        if task.get("status") != "blocked":
                            report["dependency_blocked"] += 1
                        task["status"] = "blocked"
                        details.update({
                            "workflow_auto_blocked": True,
                            "work_type": "blocked",
                            "blocker": "Waiting for: " + "; ".join(unresolved[:5]),
                            "next_action": "Complete the listed prerequisite work, then run the manager review again.",
                        })
                    elif task.get("status") == "blocked" and details.get("workflow_auto_blocked"):
                        task["status"] = "queued"
                        for key in ("workflow_auto_blocked", "blocker", "next_action"):
                            details.pop(key, None)
                        details["work_type"] = "agent_work"
                        report["dependency_released"] += 1

                    age_hours = (now - _parse_created(task, now)).total_seconds() / 3600
                    if age_hours >= stale_hours and task.get("status") == "queued":
                        if PRIORITY_ORDER.get(task.get("priority", "NORMAL"), 2) > PRIORITY_ORDER["HIGH"]:
                            task["priority"] = "HIGH"
                            report["stale_promoted"] += 1
                        details.setdefault("blocker", f"Queued for more than {stale_hours} hours without completion.")
                        details.setdefault("next_action", "Manager should confirm the owner, scope, and prerequisites.")
                        details.setdefault("work_type", "stale_work")

                for completed_task in completed[-200:]:
                    if not _result_needs_review(completed_task):
                        continue
                    completed_at = _parse_created(
                        {"created_at": completed_task.get("completed_at")}, now
                    )
                    if now - completed_at > timedelta(days=7):
                        continue
                    source_id = str(completed_task.get("id") or completed_task.get("task_id"))
                    key = f"completion_review:{source_id}"
                    if key in existing_review_keys:
                        continue
                    source_details = _task_details(completed_task)
                    client = _clean(source_details.get("client_name"), 120) or "General"
                    title = f"Manager review: {_clean(completed_task.get('title'), 140)}"
                    task_id = "task_workflow_" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:20]
                    follow_up = {
                        "id": task_id,
                        "title": title,
                        "requester": "Marley",
                        "assigned_agent": "Attorney",
                        "priority": "HIGH",
                        "status": "waiting_on_human",
                        "created_at": now.isoformat(),
                        "details": {
                            "client_name": None if client == "General" else client,
                            "work_type": "completion_review",
                            "requires_human": True,
                            "owner": "Attorney",
                            "due_date": today,
                            "review_key": key,
                            "source_task_id": source_id,
                            "blocker": "The agent marked the source task completed but reported unconfirmed or failed work.",
                            "next_action": "Review the source result, correct its scope or inputs, and decide whether to requeue it.",
                        },
                    }
                    active.append(follow_up)
                    existing_review_keys.add(key)
                    report["completion_reviews"] += 1
                    calendar_requests.append({
                        "event_key": key,
                        "title": title,
                        "date": today,
                        "client_name": client,
                        "priority": "HIGH",
                        "kind": "completion_review",
                        "source_task_id": task_id,
                        "blocker": follow_up["details"]["blocker"],
                        "next_action": follow_up["details"]["next_action"],
                    })

                board._append_activity(
                    payload,
                    "[MARLEY] Daily advancement review refreshed priorities, blockers, and human follow-ups.",
                )

            board._locked_mutation(mutate)
            for request in calendar_requests:
                _event, created = calendar.upsert_event(**request)
                report["calendar_upserts"] += int(created)
            state = {
                "last_review_date": today,
                "last_reviewed_at": now.isoformat(),
                "last_report": report,
            }
            atomic_write_json(state_path, state)
            return report
        finally:
            fcntl.flock(state_lock, fcntl.LOCK_UN)


def _due_date(value) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _item_sort_key(item: dict):
    due = _due_date(item.get("due_date"))
    status_rank = {
        "waiting_on_human": 0, "failed": 1, "blocked": 2,
        "queued": 3, "in_progress": 4, "open": 5,
    }.get(item.get("status"), 6)
    return (
        0 if item.get("overdue") else 1,
        PRIORITY_ORDER.get(item.get("priority", "NORMAL"), 2),
        status_rank,
        due or date.max,
        item.get("title", ""),
    )


def _safe_normalize_slug(value) -> str | None:
    try:
        return normalize_slug(str(value)) if value else None
    except ValueError:
        return None


def _review_target(details: dict, cases_by_slug: dict, cases_by_name: dict) -> dict | None:
    """Resolve task metadata to an opaque matter/file target safe for the browser."""
    requested_slug = _safe_normalize_slug(details.get("client_slug"))
    client_name = _clean(details.get("client_name"), 120)
    case = cases_by_slug.get(requested_slug) if requested_slug else None
    if case is None and client_name:
        case = cases_by_name.get(client_name.casefold())
        if case is None:
            case = cases_by_slug.get(_safe_normalize_slug(client_name))
    if case is None:
        return None
    slug = str(case.get("client_slug", ""))
    target = {"client_slug": slug}
    case_dir = os.path.realpath(str(case.get("path", "")))
    if not os.path.isdir(case_dir):
        return target

    path_value = next((
        details.get(key) for key in (
            "file_path", "document_path", "output_path", "source_file",
            "relative_path", "file_name", "document_name", "recent_file",
        ) if isinstance(details.get(key), str) and details.get(key).strip()
    ), None)
    if not path_value:
        return target
    candidate = None
    try:
        if os.path.isabs(path_value):
            absolute = os.path.realpath(path_value)
            if os.path.commonpath([case_dir, absolute]) == case_dir:
                candidate = absolute
        else:
            candidate = resolve_within(case_dir, path_value)
    except (OSError, ValueError):
        candidate = None
    if candidate and not os.path.isfile(candidate) and os.path.basename(path_value) == path_value:
        matches = []
        for root, directories, files in os.walk(case_dir):
            directories[:] = [name for name in directories if not name.startswith(".")]
            if path_value in files:
                matches.append(os.path.join(root, path_value))
            if len(matches) > 1:
                break
        candidate = matches[0] if len(matches) == 1 else None
    if candidate and os.path.isfile(candidate):
        relative = os.path.relpath(candidate, case_dir)
        hidden = any(part.startswith(".") for part in relative.replace("\\", "/").split("/"))
        if not hidden and not path_is_sensitive(candidate, root=case_dir):
            target["file_path"] = relative.replace(os.sep, "/")
            target["file_name"] = os.path.basename(candidate)
    return target


def build_workstation_items(
    *, board: OfficeBoard | None = None, calendar: LocalCalendar | None = None,
    database: OfficeSQLite | None = None, today: date | None = None,
) -> list[dict]:
    """Return a browser-safe, priority-sorted view of work, reminders, and case blockers."""
    board = board or OfficeBoard()
    calendar = calendar or LocalCalendar()
    database = database or OfficeSQLite()
    today = today or date.today()
    items = []
    linked_event_tasks = set()
    case_records = database.list_all_cases()
    cases_by_slug = {
        str(case.get("client_slug")): case for case in case_records if case.get("client_slug")
    }
    cases_by_name = {
        str(case.get("client_name", "")).casefold(): case
        for case in case_records if case.get("client_name")
    }
    all_board_tasks = board.board.get("active_tasks", []) + board.board.get("completed_tasks", [])
    board_tasks_by_id = {
        str(task.get("id") or task.get("task_id")): task for task in all_board_tasks
    }

    for task in board.board.get("active_tasks", []):
        details = _task_details(task)
        target_details = dict(details)
        source_task = board_tasks_by_id.get(str(details.get("source_task_id", "")))
        if source_task:
            source_details = _task_details(source_task)
            for key in (
                "client_name", "client_slug", "file_path", "document_path", "output_path",
                "source_file", "relative_path", "file_name", "document_name", "recent_file",
            ):
                if not target_details.get(key) and source_details.get(key):
                    target_details[key] = source_details[key]
        target = _review_target(target_details, cases_by_slug, cases_by_name)
        task_id = str(task.get("id") or task.get("task_id"))
        due = details.get("due_date")
        due_value = _due_date(due)
        requires_human = bool(details.get("requires_human"))
        client_name = target_details.get("client_name")
        client_slug = target.get("client_slug") if target else _safe_normalize_slug(client_name)
        form_spec = details.get("interactive_form")
        banner_spec = details.get("alert_banner")
        user_responses = details.get("user_responses")
        validated_widgets = validate_widget_schema({
            "interactive_form": form_spec,
            "alert_banner": banner_spec,
        }) if (form_spec or banner_spec) else {}

        items.append({
            "id": task_id,
            "title": _clean(task.get("title"), 200),
            "kind": _clean(details.get("work_type"), 60) or "agent_work",
            "owner": _clean(details.get("owner") or task.get("assigned_agent"), 80) or "Office",
            "matter": _clean(client_name, 120) or None,
            "client_slug": client_slug,
            "review_target": target,
            "priority": task.get("priority", "NORMAL"),
            "status": task.get("status", "queued"),
            "due_date": due,
            "overdue": bool(due_value and due_value < today and task.get("status") != "completed"),
            "blocker": _clean(details.get("blocker"), 500) or None,
            "next_action": _clean(details.get("next_action"), 500) or None,
            "requires_human": requires_human,
            "can_complete": requires_human and task.get("status") == "waiting_on_human",
            "can_snooze": requires_human and task.get("status") == "waiting_on_human",
            "interactive_form": validated_widgets.get("interactive_form"),
            "alert_banner": validated_widgets.get("alert_banner"),
            "user_responses": user_responses if isinstance(user_responses, dict) else None,
            "source": "office_board",
        })
        linked_event_tasks.add(task_id)

    for event in calendar.list_events():
        source_task_id = event.get("source_task_id")
        if source_task_id and source_task_id in linked_event_tasks:
            continue
        due = event.get("date")
        due_value = _due_date(due)
        event_matter = event.get("client_name")
        event_target = _review_target(event, cases_by_slug, cases_by_name)
        event_slug = event_target.get("client_slug") if event_target else _safe_normalize_slug(event_matter)
        items.append({
            "id": str(event.get("id")),
            "title": _clean(event.get("title"), 200),
            "kind": _clean(event.get("kind"), 60) or "calendar_event",
            "owner": "Office",
            "matter": _clean(event_matter, 120) or None,
            "client_slug": event_slug,
            "review_target": event_target,
            "priority": event.get("priority", "NORMAL"),
            "status": event.get("status", "open"),
            "due_date": due,
            "overdue": bool(due_value and due_value < today),
            "blocker": _clean(event.get("blocker"), 500) or None,
            "next_action": _clean(event.get("next_action"), 500) or None,
            "requires_human": event.get("kind") in {"human_follow_up", "completion_review"},
            "can_complete": False,
            "can_snooze": False,
            "source": "calendar",
        })

    for case in case_records:
        category = str(case.get("category", "")).replace("\\", "/").lower()
        if (str(case.get("status", "open")).lower() == "closed"
                or "/closed/" in f"/{category.strip('/')}/"):
            continue
        state_path = os.path.join(str(case.get("path", "")), ".client_file_state.json")
        try:
            with open(state_path, "r", encoding="utf-8") as handle:
                case_state = json.load(handle)
        except (OSError, json.JSONDecodeError):
            continue
        client_name = _clean(case_state.get("client_name") or case.get("client_name"), 120)
        case_slug = _clean(case.get("client_slug"), 120)
        steps = [
            cleaned for cleaned in (
                _clean(step, 300) for step in (case_state.get("next_steps") or [])[:5]
            ) if cleaned
        ]
        missing = []
        for name, info in (case_state.get("required_documents") or {}).items():
            status = info.get("status", "not_started") if isinstance(info, dict) else "not_started"
            if str(status).lower() not in {"dispatched", "filed", "on_file", "completed", "done"}:
                missing.append(_clean(name, 120))
        if steps or missing:
            urgent = any(
                re.search(r"\b(deadline|hearing|file|urgent|emergency)\b", step, re.I)
                for step in steps
            )
            items.append({
                "id": _review_key("case_advancement", str(case.get("client_slug"))),
                "title": f"Advance {client_name or 'matter'}",
                "kind": "case_advancement",
                "owner": "Matter team",
                "matter": client_name,
                "client_slug": case_slug,
                "review_target": {"client_slug": case_slug},
                "priority": "HIGH" if missing or urgent else "NORMAL",
                "status": "blocked" if missing else "open",
                "due_date": None,
                "overdue": False,
                "blocker": (
                    f"Required documents outstanding ({len(missing)}): " + ", ".join(missing[:5])
                    if missing else None
                ),
                "next_action": (
                    " ".join(f"{index + 1}. {step}" for index, step in enumerate(steps[:3]))
                    if steps else "Confirm the outstanding documents and assign collection or drafting work."
                ),
                "requires_human": False,
                "can_complete": False,
                "can_snooze": False,
                "source": "case_record",
            })

    return sorted(items, key=_item_sort_key)[:200]


def complete_human_task(task_id: str, *, board: OfficeBoard | None = None,
                        calendar: LocalCalendar | None = None) -> None:
    board = board or OfficeBoard()
    calendar = calendar or LocalCalendar()
    task = next((item for item in board.board.get("active_tasks", []) if item.get("id") == task_id), None)
    if not task or not _task_details(task).get("requires_human"):
        raise ValueError("Only an active human follow-up can be completed here.")
    board.update_task_status(task_id, "completed", result="Completed by staff in the local workstation.")
    calendar.complete_for_task(task_id)


def submit_human_form_response(
    task_id: str,
    responses: dict,
    *,
    board: OfficeBoard | None = None,
    calendar: LocalCalendar | None = None,
) -> dict:
    """Record user input responses for an agent request form and re-queue the task."""
    if not isinstance(responses, dict):
        raise ValueError("Responses must be a dictionary.")

    board = board or OfficeBoard()
    calendar = calendar or LocalCalendar()
    task_found = [None]

    def mutate(payload):
        task = next((item for item in payload.get("active_tasks", []) if item.get("id") == task_id), None)
        if not task:
            raise ValueError(f"Active task '{task_id}' not found.")
        details = _task_details(task)

        existing_responses = details.get("user_responses")
        if not isinstance(existing_responses, dict):
            existing_responses = {}
        existing_responses.update(responses)
        details["user_responses"] = existing_responses

        task["status"] = "queued"
        details["requires_human"] = False
        details["workflow_auto_blocked"] = False
        details.pop("blocker", None)
        details["next_action"] = "User form responses provided. Agent will process updated inputs."
        task_found[0] = task

        board._append_activity(
            payload,
            f"[WORKSTATION] Form responses submitted for task '{task.get('title')}'. Requeued for agent processing."
        )

    board._locked_mutation(mutate)
    calendar.complete_for_task(task_id)
    return task_found[0] or {}


def snooze_human_task(task_id: str, due_date: str, *, board: OfficeBoard | None = None,
                      calendar: LocalCalendar | None = None) -> None:
    try:
        parsed = date.fromisoformat(str(due_date))
    except ValueError as exc:
        raise ValueError("Snooze date must use YYYY-MM-DD.") from exc
    if parsed < date.today() or parsed > date.today() + timedelta(days=3650):
        raise ValueError("Snooze date must be today or within the next ten years.")
    board = board or OfficeBoard()
    calendar = calendar or LocalCalendar()

    def mutate(payload):
        task = next((item for item in payload.get("active_tasks", []) if item.get("id") == task_id), None)
        if not task or not _task_details(task).get("requires_human"):
            raise ValueError("Only an active human follow-up can be snoozed here.")
        _task_details(task)["due_date"] = parsed.isoformat()
        board._append_activity(payload, f"[WORKSTATION] Snoozed human follow-up '{task.get('title')}'.")

    board._locked_mutation(mutate)
    calendar.snooze_for_task(task_id, parsed.isoformat())


def main(argv=None) -> int:
    """Small operator entry point for a safe, local, on-demand review."""
    import argparse

    parser = argparse.ArgumentParser(description="Refresh AIMAOS priorities and blockers.")
    parser.add_argument("--force", action="store_true", help="Run even if today's review already ran.")
    args = parser.parse_args(argv)
    print(json.dumps(run_daily_advancement_review(force=args.force), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

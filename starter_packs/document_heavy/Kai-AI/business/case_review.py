"""Runs a case's review agent and applies the full result -- shared by
manage_case_records' review action and process_incoming_file, so a review
triggered either way (periodic housekeeping vs. something just arrived)
gets the same follow-through: the case file update, any follow-up tasks
posted to the Office Board, any deadlines added to Marley's calendar, and
any client notification posted as a task for Finn. Keeping this in one
place means those hand-offs can never quietly happen for one trigger path
and not the other.
"""
import os

def _find_aimaos_root():
    p = os.path.dirname(os.path.abspath(__file__))
    while p != os.path.dirname(p) and not os.path.exists(os.path.join(p, "aimaos_config.yaml")):
        p = os.path.dirname(p)
    return p
AIMAOS_ROOT = os.environ.get("AIMAOS_ROOT") or _find_aimaos_root()
import sys
import importlib.util

sys.path.insert(0, os.path.join(AIMAOS_ROOT, "Kai-AI"))
from business import client_file

sys.path.insert(0, AIMAOS_ROOT)
from core.case_agent import CaseAgent
from core.comms.office_board import OfficeBoard
from core.office_agent import load_office_config

_RECORD_FILES = {"CLIENT_FILE.md", ".client_file_state.json"}
_MAX_LISTING_ENTRIES = 200


def _load_cross_agent_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def directory_listing(case_dir):
    entries = []
    for root, dirs, files in os.walk(case_dir):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]
        for f in files:
            if f in _RECORD_FILES:
                continue
            full = os.path.join(root, f)
            rel = os.path.relpath(full, case_dir)
            entries.append(f"- {rel} ({os.path.getsize(full)} bytes)")
            if len(entries) >= _MAX_LISTING_ENTRIES:
                return "\n".join(entries) + "\n... (truncated)"
    return "\n".join(entries) if entries else "(directory is otherwise empty)"


def roster():
    cfg = load_office_config()
    return {name: info.get("role", name) for name, info in cfg.get("agents", {}).items()}


def run_review_and_apply(client_name):
    """Runs the case's review agent and applies everything it identified.
    Returns (report_lines, update_dict). update_dict is {} if the review
    produced nothing usable."""
    md = client_file.get_markdown(client_name)
    if md is None:
        return ([f"Error: no case record exists yet for {client_name}; use action=create first."], {})

    case_dir = client_file.resolve_client_dir(client_name)
    listing = directory_listing(case_dir)
    case_agent = CaseAgent(case_dir, client_name)
    update = case_agent.review(md, listing, available_agents=roster())

    if not update:
        return ([f"Review ran for {client_name} but produced no usable update (see logs)."], {})

    # --- last write to the case folder happens here ---
    client_file.update_status(
        client_name,
        summary=update.get("summary"),
        next_steps=update.get("next_steps"),
        required_documents=update.get("required_documents"),
    )
    client_file.mark_reviewed(client_name)
    # --- everything below only touches the Office Board / calendar / a
    # draft message -- never the case folder again ---

    changed = [k for k in ("summary", "next_steps", "required_documents") if update.get(k) is not None]
    report = [f"Case agent for {client_name} reviewed the directory and updated: {', '.join(changed) or 'nothing'}."]

    board = OfficeBoard()
    for task in update.get("tasks_to_assign") or []:
        task_id = board.post_task(
            title=task.get("title", f"Follow-up for {client_name}"),
            requester="Kai",
            target_agent=task["agent"],
            priority="HIGH",
            details={"client_name": client_name, "description": task.get("description", "")},
        )
        report.append(f"- Posted task {task_id} to {task['agent']}: {task.get('title')}")

    if update.get("deadlines"):
        schedule_mod = _load_cross_agent_module(
            "kai_manage_schedule", os.path.join(AIMAOS_ROOT, "Marley-AI/tools/manage_schedule.py"))
        for deadline in update["deadlines"]:
            res = schedule_mod.execute(action="add_event", event_title=deadline.get("description"),
                                       date=deadline.get("date"), client_name=client_name)
            report.append(f"- Calendar: {res}")

    notification = update.get("user_notification") or {}
    if notification.get("needed"):
        draft_mod = _load_cross_agent_module(
            "kai_draft_client_request", os.path.join(AIMAOS_ROOT, "shared_tools/draft_client_request.py"))
        channel = client_file.get_preferred_channel(client_name)
        draft = draft_mod.execute(
            client_name=client_name,
            case_context=notification.get("reason", "your matter"),
            needed_fields=notification.get("needed_info") or ["confirmation to proceed"],
            reason=notification.get("reason"),
        )
        channel_note = channel or "not specified — email is the only channel currently wired"
        task_id = board.post_task(
            title=f"Send update to {client_name}",
            requester="Kai",
            target_agent="Finn",
            priority="NORMAL",
            details={"client_name": client_name, "channel": channel_note, "draft_message": draft},
        )
        report.append(f"- Posted notification task {task_id} to Finn (channel: {channel_note})")

    return (report, update)

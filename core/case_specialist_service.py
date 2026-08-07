"""AIMAOS adapter for the host-neutral case-specialist state engine."""
from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Callable, Mapping

from core.atomic_io import atomic_write_json, atomic_write_text
from core.case_specialist import (
    ApplyResult,
    CaseReviewLock,
    ReviewProposal,
    action_key,
    build_review_context,
    default_state,
    detect_changes,
    inventory_case,
    inventory_digest,
    load_state,
    save_state,
    state_path,
    utc_now,
)
from core.document_text import extract_document_text
from core.security import normalize_slug, require_allowed_path


def load_office_config() -> dict:
    """Load office configuration lazily so deterministic core tests stay host-neutral."""
    from core.office_agent import load_office_config as loader
    return loader()


def resolve_case(case_reference: str, client_name: str | None = None) -> tuple[str, str, str, str]:
    """Resolve an approved path or SQLite case identifier.

    Returns ``(case_id, case_dir, client_name, category)`` without exposing a
    local path through user-facing output.
    """
    if os.path.isdir(str(case_reference)):
        case_dir = require_allowed_path(str(case_reference))
        case_id = normalize_slug(client_name or os.path.basename(case_dir), label="case identifier")
        return case_id, case_dir, client_name or os.path.basename(case_dir), "general"

    case_id = normalize_slug(str(case_reference), label="case identifier")
    from core.db.office_sqlite import OfficeSQLite

    case = OfficeSQLite().get_case(case_id)
    if not case:
        raise FileNotFoundError(f"No AIMAOS matter exists for identifier '{case_id}'.")
    case_dir = require_allowed_path(str(case.get("path")), must_exist=True)
    return (
        case_id,
        case_dir,
        client_name or str(case.get("client_name") or case_id),
        str(case.get("category") or "general"),
    )


def _load_record(case_dir: str, client_name: str, category: str) -> dict:
    path = os.path.join(case_dir, ".client_file_state.json")
    try:
        with open(path, "r", encoding="utf-8") as handle:
            record = json.load(handle)
        if not isinstance(record, dict):
            raise ValueError("case state is not an object")
    except (OSError, ValueError, json.JSONDecodeError):
        record = {
            "client_name": client_name,
            "matter_type": "Document Intake",
            "category": category,
            "case_number": None,
            "opened": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "state": "open",
            "summary": "",
            "next_steps": [],
            "required_documents": {},
            "candidate_dates": [],
            "activity_log": [],
            "last_reviewed_at": None,
            "preferred_channel": None,
        }
    record.setdefault("client_name", client_name)
    record.setdefault("category", category)
    record.setdefault("activity_log", [])
    record.setdefault("candidate_dates", [])
    return record


def _render_record(record: Mapping) -> str:
    lines = [
        f"# Client File: {record.get('client_name')}",
        "",
        "> AI-generated working overview. Verify all facts, dates, and next steps.",
        "",
        f"**Matter:** {record.get('matter_type') or 'Unspecified'}",
        f"**Case Number:** {record.get('case_number') or 'Not yet assigned'}",
        f"**State:** {record.get('state') or 'open'}",
        f"**Category:** {record.get('category') or 'Uncategorized'}",
        f"**Opened:** {record.get('opened') or 'Unknown'}",
        f"**Last Updated:** {record.get('last_updated') or 'Unknown'}",
        f"**Last Reviewed:** {record.get('last_reviewed_at') or 'Never'}",
        "",
        "## Status Summary",
        "",
        str(record.get("summary") or "*No summary yet.*"),
        "",
        "## Next Steps",
        "",
    ]
    steps = record.get("next_steps") or []
    lines.extend(f"- {step}" for step in steps[:5])
    if not steps:
        lines.append("*None recorded.*")

    lines.extend(["", "## Required Documents", ""])
    documents = record.get("required_documents") or {}
    for name, value in list(documents.items())[:100]:
        if isinstance(value, Mapping):
            status = value.get("status", "not_started")
            document_path = value.get("path")
        else:
            status, document_path = value, None
        checked = "x" if str(status).lower() in {"dispatched", "filed", "on_file", "completed", "done"} else " "
        path_note = f" — {document_path}" if document_path else ""
        lines.append(f"- [{checked}] {name} — {status}{path_note}")
    if not documents:
        lines.append("*None recorded.*")

    lines.extend(["", "## Candidate Dates — Staff Verification Required", ""])
    dates = record.get("candidate_dates") or []
    for item in dates[:20]:
        if not isinstance(item, Mapping):
            continue
        source = f" — source: {item.get('source_path')}" if item.get("source_path") else ""
        lines.append(f"- {item.get('date') or 'Unverified date'} — {item.get('description') or 'Candidate date'}{source}")
    if not dates:
        lines.append("*None identified. Confirm dates independently.*")

    lines.extend(["", "## Activity Log", ""])
    activity = record.get("activity_log") or []
    lines.extend(
        f"- {entry.get('timestamp', 'Unknown')} — {entry.get('entry', '')}"
        for entry in activity[-200:] if isinstance(entry, Mapping)
    )
    if not activity:
        lines.append("*No activity yet.*")
    lines.append("")
    return "\n".join(lines)


def _apply_overview(case_dir: str, record: dict, proposal: ReviewProposal, digest: str) -> tuple[str, ...]:
    changed: list[str] = []
    provided = set(proposal.provided_fields)
    if "summary" in provided:
        record["summary"] = proposal.summary or ""
        changed.append("summary")
    if "next_steps" in provided:
        record["next_steps"] = list(proposal.next_steps)
        changed.append("next_steps")
    if "required_documents" in provided:
        existing = record.setdefault("required_documents", {})
        for name, status in proposal.required_documents.items():
            prior = existing.get(name)
            if isinstance(prior, Mapping):
                prior = dict(prior)
                prior["status"] = status
                existing[name] = prior
            else:
                existing[name] = {"status": status}
        changed.append("required_documents")
    if "candidate_dates" in provided:
        record["candidate_dates"] = [dict(item) for item in proposal.candidate_dates]
        changed.append("candidate_dates")
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    record["last_updated"] = now
    record["last_reviewed_at"] = now
    record.setdefault("activity_log", []).append({
        "timestamp": now,
        "entry": f"Case specialist refreshed the working overview from digest {digest[:12]}.",
    })
    atomic_write_json(os.path.join(case_dir, ".client_file_state.json"), record)
    atomic_write_text(os.path.join(case_dir, "CLIENT_FILE.md"), _render_record(record))
    return tuple(changed)


def _snapshot_overview(case_dir: str) -> dict[str, str | None]:
    snapshot = {}
    for name in (".client_file_state.json", "CLIENT_FILE.md"):
        path = os.path.join(case_dir, name)
        try:
            with open(path, "r", encoding="utf-8") as handle:
                snapshot[name] = handle.read()
        except FileNotFoundError:
            snapshot[name] = None
    return snapshot


def _restore_overview(case_dir: str, snapshot: Mapping[str, str | None]) -> None:
    for name, content in snapshot.items():
        path = os.path.join(case_dir, name)
        if content is None:
            try:
                os.unlink(path)
            except FileNotFoundError:
                pass
        else:
            atomic_write_text(path, content)


def _roster() -> dict[str, str]:
    config = load_office_config()
    return {
        str(name): str((info or {}).get("role") or name)
        for name, info in (config.get("agents") or {}).items()
        if isinstance(info, Mapping)
    }


def _default_review_binding(
    case_dir: str, client_name: str, category: str, *, record_experience: bool = True
):
    from core.case_agent import CaseAgent

    agent = CaseAgent(case_dir, client_name, category=category)
    prior_memory = agent._prior_review_context()

    def review(context, *, client_name: str, category: str):
        evidence_parts = []
        for item in context.evidence:
            evidence_parts.append(
                f"<CHANGED_FILE path={json.dumps(item.get('path'))} status={json.dumps(item.get('status'))}>\n"
                f"{item.get('text') or '[No safe extracted text available.]'}\n</CHANGED_FILE>"
            )
        return agent.review(
            context.current_overview,
            context.directory_listing,
            available_agents=context.roster,
            document_excerpt="\n\n".join(evidence_parts) if evidence_parts else None,
            prior_review_context=prior_memory,
            record_experience=record_experience,
        )

    return prior_memory, review


def _existing_action_keys(board) -> set[str]:
    keys = set()
    for task in board.board.get("active_tasks", []) + board.board.get("completed_tasks", []):
        details = task.get("details")
        if isinstance(details, Mapping) and details.get("case_specialist_key"):
            keys.add(str(details["case_specialist_key"]))
    return keys


def _post_internal_actions(
    proposal: ReviewProposal,
    *,
    case_id: str,
    client_name: str,
    digest: str,
    state: dict,
    roster: Mapping[str, str],
    board=None,
) -> tuple[list[dict], list[dict], list[dict], list[str]]:
    config = load_office_config()
    gate_enabled = bool((config.get("security") or {}).get("allow_document_delegation", False))
    warnings: list[str] = []
    posted: list[dict] = []
    dropped: list[dict] = []
    verification: list[dict] = []
    if proposal.user_notification and proposal.user_notification.get("needed"):
        warnings.append("External notification was suppressed; the plugin never sends communications.")
    if not gate_enabled:
        if proposal.tasks or proposal.candidate_dates:
            warnings.append("Internal actions were not posted because allow_document_delegation is disabled.")
        skipped = [dict(item, reason="delegation disabled") for item in proposal.tasks]
        skipped.extend(
            dict(item, reason="delegation disabled; staff date verification not posted")
            for item in proposal.candidate_dates
        )
        return posted, skipped, verification, warnings

    if board is None:
        from core.comms.office_board import OfficeBoard
        board = OfficeBoard()
    known_keys = set(str(item) for item in state.get("posted_action_keys") or [])
    known_keys.update(_existing_action_keys(board))

    for task in proposal.tasks:
        if task.get("agent") not in roster:
            dropped.append(dict(task))
            continue
        key = action_key(case_id, digest, "assignment", task["agent"], task["title"], task.get("description", ""))
        if key in known_keys:
            dropped.append({**dict(task), "reason": "duplicate"})
            continue
        task_id = board.post_task(
            task["title"], "CaseSpecialist", task["agent"], "HIGH",
            details={
                "client_name": client_name,
                "client_slug": case_id,
                "description": task.get("description", ""),
                "work_type": "case_specialist_follow_up",
                "case_specialist_key": key,
                "source_digest": digest,
            },
        )
        known_keys.add(key)
        posted.append({**dict(task), "task_id": task_id})

    verification_agent = "Marley" if "Marley" in roster else next(iter(roster), None)
    for candidate in proposal.candidate_dates:
        if not verification_agent:
            dropped.append({**dict(candidate), "reason": "no roster agent available for verification"})
            continue
        key = action_key(
            case_id, digest, "date-verification", candidate.get("date", ""),
            candidate.get("description", ""), candidate.get("source_path", ""),
        )
        if key in known_keys:
            continue
        title = f"Verify candidate date: {candidate.get('date') or 'unverified'}"
        task_id = board.post_task(
            title, "CaseSpecialist", verification_agent, "HIGH",
            details={
                "client_name": client_name,
                "client_slug": case_id,
                "description": candidate.get("description", "Candidate date requires staff verification."),
                "source_path": candidate.get("source_path"),
                "candidate_date": candidate.get("date"),
                "requires_human": True,
                "work_type": "deadline_verification",
                "case_specialist_key": key,
                "source_digest": digest,
                "next_action": "Verify this date against an authoritative source before calendaring or relying on it.",
            },
        )
        known_keys.add(key)
        verification.append({**dict(candidate), "task_id": task_id})

    state["posted_action_keys"] = sorted(known_keys)[-1_000:]
    return posted, dropped, verification, warnings


def initialize_case(case_reference: str, *, client_name: str | None = None) -> dict:
    case_id, case_dir, resolved_name, category = resolve_case(case_reference, client_name)
    state = load_state(case_dir, case_id)
    if not os.path.isfile(state_path(case_dir)):
        save_state(case_dir, state)
    changes, _inventory = detect_changes(case_dir, case_id, state)
    return {
        "status": "initialized",
        "case_id": case_id,
        "client_name": resolved_name,
        "category": category,
        "changes": changes.to_dict(),
    }


def case_status(case_reference: str, *, client_name: str | None = None) -> dict:
    case_id, case_dir, resolved_name, category = resolve_case(case_reference, client_name)
    state = load_state(case_dir, case_id)
    changes, _inventory = detect_changes(case_dir, case_id, state)
    return {
        "status": "dirty" if changes.has_changes else "current",
        "case_id": case_id,
        "client_name": resolved_name,
        "category": category,
        "last_reviewed_at": state.get("last_reviewed_at"),
        "last_error": state.get("last_error"),
        "last_failure_at": state.get("last_failure_at"),
        "queued_digest": state.get("queued_digest"),
        "in_flight_digest": state.get("in_flight_digest"),
        "changes": changes.to_dict(),
    }


def audit_case(case_reference: str, *, client_name: str | None = None) -> dict:
    status = case_status(case_reference, client_name=client_name)
    _case_id, case_dir, _resolved_name, _category = resolve_case(case_reference, client_name)
    lock_path = os.path.join(case_dir, ".case_agent", "review.lock")
    findings = []
    if os.path.isfile(lock_path):
        findings.append({"kind": "review_lock", "age_seconds": max(0, int(datetime.now().timestamp() - os.path.getmtime(lock_path)))})
    findings.extend({"kind": "inventory_warning", "message": item} for item in status["changes"]["warnings"])
    if status.get("last_error"):
        findings.append({"kind": "last_review_error", "message": status["last_error"]})
    return {**status, "status": "attention_required" if findings else status["status"], "findings": findings}


def refresh_case(
    case_reference: str,
    *,
    client_name: str | None = None,
    force: bool = False,
    dry_run: bool = False,
    reason: str = "manual refresh",
    reviewer: Callable | None = None,
    board=None,
) -> dict:
    case_id, case_dir, resolved_name, category = resolve_case(case_reference, client_name)
    with CaseReviewLock(case_dir):
        state = load_state(case_dir, case_id)
        changes, inventory = detect_changes(case_dir, case_id, state)
        if not changes.has_changes and not force:
            return ApplyResult(case_id, changes.current_digest, "unchanged", warnings=changes.warnings).to_dict()

        overview_path = os.path.join(case_dir, "CLIENT_FILE.md")
        try:
            with open(overview_path, "r", encoding="utf-8", errors="replace") as handle:
                overview = handle.read(250_000)
        except OSError:
            overview = "No prior case overview exists."
        roster = _roster()
        prior_memory = ""
        review_callable = reviewer
        if review_callable is None:
            prior_memory, review_callable = _default_review_binding(
                case_dir, resolved_name, category, record_experience=not dry_run
            )
        context = build_review_context(
            case_dir, case_id, changes, inventory,
            overview=overview, roster=roster, extractor=extract_document_text,
            prior_memory=prior_memory,
        )

        if not dry_run:
            state["queued_digest"] = changes.current_digest
            state["in_flight_digest"] = changes.current_digest
            state["last_error"] = None
            save_state(case_dir, state)
        try:
            raw_proposal = review_callable(
                context, client_name=resolved_name, category=category
            )
            if not raw_proposal:
                raise ValueError("case specialist produced no usable structured update")
            proposal = ReviewProposal.from_mapping(
                raw_proposal,
                roster,
                {str(item.get("path")) for item in context.evidence if item.get("path")},
            )

            latest_inventory, latest_warnings = inventory_case(case_dir, inventory)
            latest_digest = inventory_digest(latest_inventory)
            if latest_digest != changes.current_digest:
                raise RuntimeError("Case files changed while the review was running; the stale proposal was not applied.")

            if dry_run:
                return {
                    "status": "dry_run",
                    "case_id": case_id,
                    "reason": reason,
                    "changes": changes.to_dict(),
                    "context": context.to_dict(),
                    "proposal": proposal.to_dict(),
                    "warnings": list(changes.warnings) + latest_warnings + list(proposal.warnings),
                }

            overview_snapshot = _snapshot_overview(case_dir)
            try:
                record = _load_record(case_dir, resolved_name, category)
                overview_fields = _apply_overview(case_dir, record, proposal, changes.current_digest)
                posted, dropped, verification, action_warnings = _post_internal_actions(
                    proposal,
                    case_id=case_id,
                    client_name=resolved_name,
                    digest=changes.current_digest,
                    state=state,
                    roster=roster,
                    board=board,
                )
            except Exception:
                _restore_overview(case_dir, overview_snapshot)
                raise
            newest_state = load_state(case_dir, case_id)
            newest_keys = set(newest_state.get("posted_action_keys") or [])
            newest_keys.update(state.get("posted_action_keys") or [])
            pending_digest = newest_state.get("queued_digest")
            state = newest_state
            state["inventory"] = latest_inventory
            state["last_successful_digest"] = changes.current_digest
            state["queued_digest"] = (
                pending_digest if pending_digest and pending_digest != changes.current_digest else None
            )
            state["in_flight_digest"] = None
            state["last_reviewed_at"] = utc_now()
            state["last_error"] = None
            state["last_failure_at"] = None
            state["posted_action_keys"] = sorted(newest_keys)[-1_000:]
            save_state(case_dir, state)
            return ApplyResult(
                case_id=case_id,
                digest=changes.current_digest,
                status="applied",
                overview_fields=overview_fields,
                posted_tasks=tuple(posted),
                dropped_tasks=tuple(dropped),
                verification_tasks=tuple(verification),
                warnings=tuple(
                    list(changes.warnings) + latest_warnings + list(proposal.warnings) + action_warnings
                ),
            ).to_dict()
        except Exception as exc:
            if not dry_run:
                state = load_state(case_dir, case_id)
                try:
                    failed_inventory, _warnings = inventory_case(case_dir, state.get("inventory") or {})
                    retry_digest = inventory_digest(failed_inventory)
                except Exception:
                    retry_digest = changes.current_digest
                state["queued_digest"] = retry_digest
                state["in_flight_digest"] = None
                state["last_error"] = str(exc)[:1_000]
                state["last_failure_at"] = utc_now()
                save_state(case_dir, state)
            raise


def notify_case_changed(
    case_reference: str,
    *,
    client_name: str | None = None,
    reason: str = "AIMAOS file mutation",
    reviewer: Callable | None = None,
    board=None,
) -> dict:
    """Coalesce a file-change notification into the digest-scoped refresh."""
    try:
        result = refresh_case(
            case_reference,
            client_name=client_name,
            reason=reason,
            reviewer=reviewer,
            board=board,
        )
    except RuntimeError as exc:
        if "already in progress" not in str(exc):
            raise
        case_id, case_dir, _resolved_name, _category = resolve_case(case_reference, client_name)
        state = load_state(case_dir, case_id)
        changes, _inventory = detect_changes(case_dir, case_id, state)
        if changes.current_digest != state.get("in_flight_digest"):
            state["queued_digest"] = changes.current_digest
            save_state(case_dir, state)
        return {
            "status": "coalesced",
            "case_id": case_id,
            "digest": changes.current_digest,
            "warnings": ["A review is already in progress; this digest was coalesced."],
        }

    if result.get("status") == "applied":
        current = case_status(case_reference, client_name=client_name)
        if current.get("status") == "dirty":
            return refresh_case(
                case_reference,
                client_name=client_name,
                reason=f"Coalesced follow-up after {reason}",
                reviewer=reviewer,
                board=board,
            )
    return result

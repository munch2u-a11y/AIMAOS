"""Host-neutral state and validation primitives for matter-local specialists.

The module deliberately has no dependency on the Office Board, an LLM, or a
particular case-record implementation.  It owns the deterministic boundary:
inventorying one approved directory, detecting changes, serializing review
state, validating proposed updates, and preventing concurrent review passes.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Callable, Mapping

from core.atomic_io import atomic_write_json


SCHEMA_VERSION = 1
STATE_DIRECTORY = ".case_agent"
STATE_FILENAME = "change_state.json"
LOCK_FILENAME = "review.lock"
RECORD_FILES = {"CLIENT_FILE.md", ".client_file_state.json"}
TEMPORARY_PREFIXES = ("~$", ".aimaos-")
TEMPORARY_SUFFIXES = (".tmp", ".part", ".swp")
MAX_INVENTORY_FILES = 10_000
MAX_EVIDENCE_FILES = 5
MAX_EVIDENCE_CHARS = 100_000


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_relative_path(value: str) -> str | None:
    normalized = str(value or "").replace("\\", "/").strip()
    while normalized.startswith("./"):
        normalized = normalized[2:]
    if (
        not normalized
        or normalized.startswith("/")
        or (len(normalized) > 1 and normalized[1] == ":")
    ):
        return None
    parts = normalized.split("/")
    if any(part in {"", ".", ".."} or part.startswith(".") for part in parts):
        return None
    return normalized


def _bounded_text(value, limit: int) -> str:
    return str(value or "").strip()[:limit]


@dataclass(frozen=True)
class ChangeSet:
    case_id: str
    previous_digest: str | None
    current_digest: str
    added: tuple[str, ...] = ()
    modified: tuple[str, ...] = ()
    deleted: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def changed_paths(self) -> tuple[str, ...]:
        return self.added + self.modified + self.deleted

    @property
    def has_changes(self) -> bool:
        return self.previous_digest != self.current_digest

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["changed_paths"] = list(self.changed_paths)
        payload["has_changes"] = self.has_changes
        return payload


@dataclass(frozen=True)
class ReviewContext:
    case_id: str
    case_dir: str
    current_digest: str
    current_overview: str
    directory_listing: str
    evidence: tuple[dict, ...] = ()
    roster: dict[str, str] = field(default_factory=dict)
    prior_memory: str = ""

    def to_dict(self, *, expose_path: bool = False, include_content: bool = False) -> dict:
        payload = asdict(self)
        if not expose_path:
            payload["case_dir"] = "[approved case directory]"
        if not include_content:
            payload["current_overview"] = f"[{len(self.current_overview)} characters withheld]"
            payload["prior_memory"] = f"[{len(self.prior_memory)} characters withheld]"
            payload["evidence"] = [
                {
                    "path": item.get("path"),
                    "status": item.get("status"),
                    "detail": item.get("detail"),
                    "text_chars": len(str(item.get("text") or "")),
                }
                for item in self.evidence
            ]
        return payload


@dataclass(frozen=True)
class ReviewProposal:
    summary: str | None = None
    next_steps: tuple[str, ...] = ()
    required_documents: dict[str, str] = field(default_factory=dict)
    tasks: tuple[dict, ...] = ()
    candidate_dates: tuple[dict, ...] = ()
    user_notification: dict | None = None
    warnings: tuple[str, ...] = ()
    provided_fields: tuple[str, ...] = ()

    @classmethod
    def from_mapping(
        cls,
        value: Mapping | None,
        roster: Mapping[str, str] | None = None,
        evidence_paths: set[str] | None = None,
    ):
        if not isinstance(value, Mapping):
            raise ValueError("review proposal must be a JSON object")
        warnings: list[str] = []
        summary = _bounded_text(value.get("summary"), 10_000) or None

        raw_steps = value.get("next_steps") or []
        if not isinstance(raw_steps, list):
            warnings.append("Dropped non-list next_steps value.")
            raw_steps = []
        next_steps = tuple(
            text for text in (_bounded_text(item, 1_000) for item in raw_steps[:5]) if text
        )

        required_documents: dict[str, str] = {}
        raw_documents = value.get("required_documents") or {}
        if isinstance(raw_documents, Mapping):
            for name, status in list(raw_documents.items())[:100]:
                clean_name = _bounded_text(name, 300)
                if isinstance(status, Mapping):
                    status = status.get("status", "not_started")
                clean_status = _bounded_text(status, 500) or "not_started"
                if clean_name:
                    required_documents[clean_name] = clean_status
        elif raw_documents:
            warnings.append("Dropped non-object required_documents value.")

        allowed_agents = set((roster or {}).keys())
        tasks: list[dict] = []
        raw_tasks = value.get("tasks") or value.get("tasks_to_assign") or []
        if not isinstance(raw_tasks, list):
            warnings.append("Dropped non-list tasks value.")
            raw_tasks = []
        for task in raw_tasks[:20]:
            if not isinstance(task, Mapping):
                warnings.append("Dropped malformed task proposal.")
                continue
            agent = _bounded_text(task.get("agent"), 80)
            if allowed_agents and agent not in allowed_agents:
                warnings.append(f"Dropped task for non-roster agent: {agent or '[missing]'}.")
                continue
            title = _bounded_text(task.get("title"), 200)
            description = _bounded_text(task.get("description"), 2_000)
            if not agent or not title:
                warnings.append("Dropped task missing an agent or title.")
                continue
            tasks.append({"agent": agent, "title": title, "description": description})

        candidate_dates: list[dict] = []
        raw_dates = value.get("candidate_dates") or value.get("deadlines") or []
        if not isinstance(raw_dates, list):
            warnings.append("Dropped non-list candidate date value.")
            raw_dates = []
        for item in raw_dates[:20]:
            if not isinstance(item, Mapping):
                continue
            description = _bounded_text(item.get("description"), 800)
            date_value = _bounded_text(item.get("date"), 100)
            source_path = _safe_relative_path(item.get("source_path", ""))
            if not source_path or (evidence_paths is not None and source_path not in evidence_paths):
                warnings.append("Dropped candidate date without changed-file source evidence.")
                continue
            if description or date_value:
                candidate_dates.append({
                    "description": description or "Candidate date",
                    "date": date_value or "Unverified date",
                    "source_path": source_path,
                })

        notification = value.get("user_notification")
        if notification is not None and not isinstance(notification, Mapping):
            warnings.append("Dropped malformed user_notification value.")
            notification = None
        elif isinstance(notification, Mapping):
            notification = {
                "needed": bool(notification.get("needed")),
                "reason": _bounded_text(notification.get("reason"), 1_000),
                "needed_info": [
                    _bounded_text(item, 300)
                    for item in (notification.get("needed_info") or [])[:20]
                    if _bounded_text(item, 300)
                ],
            }

        return cls(
            summary=summary,
            next_steps=next_steps,
            required_documents=required_documents,
            tasks=tuple(tasks),
            candidate_dates=tuple(candidate_dates),
            user_notification=dict(notification) if notification else None,
            warnings=tuple(warnings),
            provided_fields=tuple(sorted(
                key for key in (
                    "summary", "next_steps", "required_documents", "tasks",
                    "candidate_dates", "user_notification",
                )
                if key in value
                or (key == "tasks" and "tasks_to_assign" in value)
                or (key == "candidate_dates" and "deadlines" in value)
            )),
        )

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ApplyResult:
    case_id: str
    digest: str
    status: str
    overview_fields: tuple[str, ...] = ()
    posted_tasks: tuple[dict, ...] = ()
    dropped_tasks: tuple[dict, ...] = ()
    verification_tasks: tuple[dict, ...] = ()
    warnings: tuple[str, ...] = ()
    error: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def state_path(case_dir: str) -> str:
    return os.path.join(os.path.realpath(case_dir), STATE_DIRECTORY, STATE_FILENAME)


def default_state(case_id: str) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "case_id": case_id,
        "inventory": {},
        "last_successful_digest": None,
        "queued_digest": None,
        "in_flight_digest": None,
        "last_reviewed_at": None,
        "last_error": None,
        "last_failure_at": None,
        "posted_action_keys": [],
        "updated_at": utc_now(),
    }


def load_state(case_dir: str, case_id: str) -> dict:
    path = state_path(case_dir)
    state = default_state(case_id)
    try:
        with open(path, "r", encoding="utf-8") as handle:
            loaded = json.load(handle)
        if isinstance(loaded, dict):
            for key in state:
                if key in loaded:
                    state[key] = loaded[key]
    except (OSError, json.JSONDecodeError):
        pass
    state["schema_version"] = SCHEMA_VERSION
    state["case_id"] = case_id
    if not isinstance(state.get("inventory"), dict):
        state["inventory"] = {}
    if not isinstance(state.get("posted_action_keys"), list):
        state["posted_action_keys"] = []
    return state


def save_state(case_dir: str, state: Mapping) -> None:
    payload = dict(state)
    payload["schema_version"] = SCHEMA_VERSION
    payload["updated_at"] = utc_now()
    atomic_write_json(state_path(case_dir), payload)


def _ignored_file(relative_path: str) -> bool:
    normalized = relative_path.replace("\\", "/")
    parts = normalized.split("/")
    name = parts[-1]
    return (
        any(part.startswith(".") for part in parts)
        or name in RECORD_FILES
        or name.startswith(TEMPORARY_PREFIXES)
        or name.endswith(TEMPORARY_SUFFIXES)
    )


def _sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inventory_case(case_dir: str, previous: Mapping[str, Mapping] | None = None) -> tuple[dict, list[str]]:
    root = os.path.realpath(case_dir)
    if not os.path.isdir(root):
        raise FileNotFoundError(f"Case directory does not exist: {case_dir}")
    previous = previous or {}
    inventory: dict[str, dict] = {}
    warnings: list[str] = []
    for walk_root, directories, files in os.walk(root):
        directories[:] = sorted(
            name for name in directories
            if not name.startswith(".") and name != "__pycache__"
        )
        for name in sorted(files):
            full_path = os.path.join(walk_root, name)
            relative = os.path.relpath(full_path, root).replace(os.sep, "/")
            if _ignored_file(relative):
                continue
            if os.path.islink(full_path):
                warnings.append(f"Skipped symbolic link: {relative}")
                continue
            real_path = os.path.realpath(full_path)
            try:
                if os.path.commonpath([root, real_path]) != root:
                    warnings.append(f"Skipped path outside case directory: {relative}")
                    continue
            except ValueError:
                warnings.append(f"Skipped path on another volume: {relative}")
                continue
            if len(inventory) >= MAX_INVENTORY_FILES:
                warnings.append(f"Inventory truncated at {MAX_INVENTORY_FILES} files.")
                return inventory, warnings
            try:
                stat = os.stat(real_path)
            except OSError as exc:
                warnings.append(f"Could not inspect {relative}: {exc}")
                continue
            prior = previous.get(relative) if isinstance(previous, Mapping) else None
            if (
                isinstance(prior, Mapping)
                and prior.get("size") == stat.st_size
                and prior.get("mtime_ns") == stat.st_mtime_ns
                and isinstance(prior.get("sha256"), str)
            ):
                file_hash = prior["sha256"]
            else:
                try:
                    file_hash = _sha256_file(real_path)
                except OSError as exc:
                    warnings.append(f"Could not hash {relative}: {exc}")
                    continue
            inventory[relative] = {
                "size": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
                "sha256": file_hash,
            }
    return inventory, warnings


def inventory_digest(inventory: Mapping[str, Mapping]) -> str:
    digest = hashlib.sha256()
    for relative, metadata in sorted(inventory.items()):
        digest.update(relative.encode("utf-8", errors="replace"))
        digest.update(b"\0")
        digest.update(str(metadata.get("sha256", "")).encode("ascii", errors="ignore"))
        digest.update(b"\n")
    return digest.hexdigest()


def detect_changes(case_dir: str, case_id: str, state: Mapping | None = None) -> tuple[ChangeSet, dict]:
    state = dict(state or load_state(case_dir, case_id))
    previous_inventory = state.get("inventory") if isinstance(state.get("inventory"), Mapping) else {}
    inventory, warnings = inventory_case(case_dir, previous_inventory)
    previous_digest = state.get("last_successful_digest")
    current_digest = inventory_digest(inventory)
    old_paths, new_paths = set(previous_inventory), set(inventory)
    added = tuple(sorted(new_paths - old_paths))
    deleted = tuple(sorted(old_paths - new_paths))
    modified = tuple(sorted(
        path for path in old_paths & new_paths
        if previous_inventory[path].get("sha256") != inventory[path].get("sha256")
    ))
    return ChangeSet(
        case_id=case_id,
        previous_digest=previous_digest,
        current_digest=current_digest,
        added=added,
        modified=modified,
        deleted=deleted,
        warnings=tuple(warnings),
    ), inventory


class CaseReviewLock:
    def __init__(self, case_dir: str, *, stale_after: int = 15 * 60):
        self.path = os.path.join(os.path.realpath(case_dir), STATE_DIRECTORY, LOCK_FILENAME)
        self.stale_after = stale_after
        self.acquired = False

    def acquire(self) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        for _attempt in range(2):
            try:
                descriptor = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError:
                try:
                    age = time.time() - os.path.getmtime(self.path)
                except OSError:
                    age = 0
                if age <= self.stale_after:
                    raise RuntimeError("A review for this case is already in progress.")
                try:
                    os.unlink(self.path)
                except FileNotFoundError:
                    pass
                continue
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump({"pid": os.getpid(), "created_at": utc_now()}, handle)
            self.acquired = True
            return
        raise RuntimeError("Could not acquire the case review lock.")

    def release(self) -> None:
        if self.acquired:
            try:
                os.unlink(self.path)
            except FileNotFoundError:
                pass
            self.acquired = False

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.release()


def build_review_context(
    case_dir: str,
    case_id: str,
    changes: ChangeSet,
    inventory: Mapping[str, Mapping],
    *,
    overview: str,
    roster: Mapping[str, str] | None = None,
    extractor: Callable[[str], object] | None = None,
    prior_memory: str = "",
) -> ReviewContext:
    root = os.path.realpath(case_dir)
    listing = "\n".join(
        f"- {path} ({metadata.get('size', 0)} bytes)"
        for path, metadata in sorted(inventory.items())
    ) or "(directory is otherwise empty)"
    evidence: list[dict] = []
    remaining = MAX_EVIDENCE_CHARS
    for relative in (changes.added + changes.modified)[:MAX_EVIDENCE_FILES]:
        safe_relative = _safe_relative_path(relative)
        if not safe_relative:
            continue
        full_path = os.path.realpath(os.path.join(root, safe_relative.replace("/", os.sep)))
        try:
            if os.path.commonpath([root, full_path]) != root or not os.path.isfile(full_path):
                continue
        except ValueError:
            continue
        item = {"path": safe_relative, "status": "metadata_only", "detail": "No extractor configured.", "text": ""}
        if extractor and remaining > 0:
            try:
                result = extractor(full_path)
                status = _bounded_text(getattr(result, "status", "manual_review_required"), 100)
                detail = _bounded_text(getattr(result, "detail", ""), 500)
                text = str(getattr(result, "text", ""))[:remaining]
                remaining -= len(text)
                item.update({"status": status, "detail": detail, "text": text})
            except Exception as exc:  # parser boundary; report without failing the inventory
                item.update({"status": "manual_review_required", "detail": _bounded_text(exc, 500)})
        evidence.append(item)
    return ReviewContext(
        case_id=case_id,
        case_dir=root,
        current_digest=changes.current_digest,
        current_overview=overview[:250_000],
        directory_listing=listing,
        evidence=tuple(evidence),
        roster=dict(roster or {}),
        prior_memory=prior_memory[:10_000],
    )


def action_key(case_id: str, digest: str, kind: str, *values: str) -> str:
    payload = "\0".join([case_id, digest, kind, *(str(value or "").strip().casefold() for value in values)])
    return hashlib.sha256(payload.encode("utf-8", errors="replace")).hexdigest()

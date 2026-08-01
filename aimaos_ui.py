#!/usr/bin/env python3
"""AIMAOS local-first public-beta dashboard and API.

The server is loopback-only by default. Model-backed work is queued outside
request threads, filesystem access uses opaque case identifiers, and mutation
requests require a same-origin CSRF token. Set ``AIMAOS_UI_TOKEN`` when using
an explicitly enabled LAN binding.
"""
from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import importlib.util
import ipaddress
import json
import logging
import mimetypes
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid
import webbrowser
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import yaml
from core.atomic_io import atomic_write_text


def _find_aimaos_root() -> str:
    path = Path(__file__).resolve()
    for parent in (path.parent, *path.parents):
        if (parent / "aimaos_config.yaml").exists():
            return str(parent)
    return str(path.parent)


AIMAOS_ROOT = os.environ.get("AIMAOS_ROOT") or _find_aimaos_root()
sys.path.insert(0, AIMAOS_ROOT)

from core.comms.office_board import OfficeBoard
from core.db.office_sqlite import OfficeSQLite
from core.document_review import DocumentReviewStore
from core.document_text import extract_document_text, validate_upload_content
from core.jobs import get_job_manager
from core.workflow_review import (
    build_workstation_items,
    complete_human_task,
    run_daily_advancement_review,
    snooze_human_task,
)
from core.version import __version__
from core.security import (
    DEFAULT_UPLOAD_EXTENSIONS,
    SecurityValidationError,
    allowed_data_roots,
    developer_mode_enabled,
    generate_csrf_token,
    load_security_config,
    normalize_slug,
    path_is_sensitive,
    require_allowed_path,
    resolve_within,
    sanitize_filename,
    sanitize_output_basename,
    token_matches,
    validate_agent_name,
    validate_slug,
)

APP_VERSION = __version__
CSRF_TOKEN = generate_csrf_token()
STARTED_AT = datetime.now().isoformat()
logger = logging.getLogger("aimaos.ui")
NOTES_LOCK = threading.Lock()
REVIEWABLE_EXTENSIONS = {".txt", ".md", ".csv", ".json", ".yaml", ".yml", ".rtf", ".docx", ".pdf"}


def _is_loopback(host: str) -> bool:
    if host in {"localhost", ""}:
        return host == "localhost"
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _templates_root() -> str:
    live = os.path.join(AIMAOS_ROOT, "Alix-AI", "templates")
    if os.path.isdir(live):
        return live
    return os.path.join(AIMAOS_ROOT, "starter_packs", "document_heavy", "Alix-AI", "templates")


def _output_root() -> str:
    root = os.path.join(AIMAOS_ROOT, "Alix-AI", "workspace", "output")
    os.makedirs(root, exist_ok=True)
    return root


def _setup_complete() -> bool:
    required_agents = {"Alix", "Kai", "Marley", "Finn"}
    return all(
        os.path.isfile(os.path.join(AIMAOS_ROOT, f"{name}-AI", "core", "agent.py"))
        for name in required_agents
    ) and os.path.isdir(_templates_root())


def _load_module(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if not spec or not spec.loader:
        raise RuntimeError(f"Could not load module at {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def load_agent(agent_name: str, class_name: str):
    path = os.path.join(AIMAOS_ROOT, f"{agent_name}-AI", "core", "agent.py")
    if not os.path.isfile(path):
        raise RuntimeError("The office is not set up yet. Run the setup wizard first.")
    module = _load_module(f"aimaos_ui_{agent_name.lower()}", path)
    return getattr(module, class_name)()


def _template_catalog() -> list[dict]:
    catalog = []
    root = _templates_root()
    if not os.path.isdir(root):
        return catalog
    for entry in sorted(os.listdir(root)):
        try:
            template_id = validate_slug(entry, label="template identifier")
        except SecurityValidationError:
            continue
        folder = resolve_within(root, entry)
        docx_path = resolve_within(folder, "template.docx")
        if not os.path.isfile(docx_path):
            continue
        metadata = {}
        metadata_path = resolve_within(folder, "template.yaml")
        if os.path.isfile(metadata_path):
            try:
                with open(metadata_path, "r", encoding="utf-8") as handle:
                    metadata = yaml.safe_load(handle) or {}
            except (OSError, yaml.YAMLError):
                metadata = {}

        fields = []
        raw_fields = metadata.get("fields") or {}
        if isinstance(raw_fields, dict):
            for field_name, field_meta in raw_fields.items():
                if not isinstance(field_name, str):
                    continue
                if isinstance(field_meta, dict):
                    fields.append({
                        "name": field_name,
                        "label": field_meta.get("label") or field_name.replace("_", " ").title(),
                        "description": field_meta.get("description", ""),
                        "required": bool(field_meta.get("required", True)),
                    })
                else:
                    fields.append({
                        "name": field_name,
                        "label": field_name.replace("_", " ").title(),
                        "description": str(field_meta or ""),
                        "required": True,
                    })
        elif isinstance(raw_fields, list):
            for field_meta in raw_fields:
                if isinstance(field_meta, dict) and field_meta.get("name"):
                    fields.append({
                        "name": field_meta["name"],
                        "label": field_meta.get("label") or field_meta["name"].replace("_", " ").title(),
                        "description": field_meta.get("description", ""),
                        "required": bool(field_meta.get("required", True)),
                    })
        provenance_complete = all(metadata.get(key) for key in (
            "jurisdiction", "revision", "official_source", "last_reviewed_at"
        ))
        catalog.append({
            "id": template_id,
            "name": metadata.get("name") or entry.replace("_", " ").title(),
            "description": metadata.get("description", ""),
            "fields": fields,
            "default_format": metadata.get("default_format", "docx"),
            "jurisdiction": metadata.get("jurisdiction"),
            "revision": metadata.get("revision"),
            "official_source": metadata.get("official_source"),
            "last_reviewed_at": metadata.get("last_reviewed_at"),
            "verification_status": "verified" if provenance_complete else "review_required",
        })
    return catalog


DAEMON_CONTROL_PATH = os.path.join(AIMAOS_ROOT, "comms", "daemon_control.json")


def _read_daemon_control() -> dict:
    try:
        with open(DAEMON_CONTROL_PATH, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {"pause_requested": False}


def _set_daemon_pause_request(paused: bool, *, requested_by: str = "user") -> dict:
    os.makedirs(os.path.dirname(DAEMON_CONTROL_PATH), exist_ok=True)
    payload = {
        "pause_requested": paused,
        "requested_by": requested_by,
        "updated_at": datetime.now().isoformat(),
    }
    temp_path = DAEMON_CONTROL_PATH + f".{os.getpid()}.tmp"
    with open(temp_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
    os.replace(temp_path, DAEMON_CONTROL_PATH)
    return payload


def _daemon_status() -> dict:
    path = os.path.join(AIMAOS_ROOT, "comms", "daemon_status.json")
    control = _read_daemon_control()
    pause_requested = bool(control.get("pause_requested"))
    try:
        with open(path, "r", encoding="utf-8") as handle:
            status = json.load(handle)
        heartbeat = datetime.fromisoformat(status.get("last_heartbeat", ""))
        process_alive = False
        try:
            os.kill(int(status.get("pid")), 0)
            process_alive = True
        except (OSError, TypeError, ValueError):
            pass
        status["responsive"] = process_alive or (datetime.now() - heartbeat).total_seconds() < 90
        status["pause_requested"] = pause_requested
        if pause_requested and status.get("state") in {"polling", "working", "ready"}:
            status["pause_pending"] = True
        return status
    except (OSError, ValueError, json.JSONDecodeError):
        return {"state": "not_running", "responsive": False, "pause_requested": pause_requested, "last_heartbeat": None}


def _unique_destination(folder: str, filename: str) -> str:
    candidate = resolve_within(folder, filename)
    if not os.path.exists(candidate):
        return candidate
    stem, extension = os.path.splitext(filename)
    return resolve_within(folder, f"{stem}_{uuid.uuid4().hex[:8]}{extension}")


def _public_case(case: dict) -> dict:
    """Return case metadata safe for browser clients (never local paths)."""
    allowed = {
        "client_slug", "client_name", "matter_type", "category", "status",
        "case_number", "opened_at", "updated_at",
    }
    return {key: value for key, value in case.items() if key in allowed}


def _public_task(task: dict) -> dict:
    """Expose progress metadata, not model arguments, paths, or raw results."""
    allowed = {
        "id", "task_id", "title", "assigned_agent", "priority", "status",
        "created_at", "updated_at", "completed_at",
    }
    return {key: value for key, value in task.items() if key in allowed}


def _browser_safe_value(value):
    """Remove configured local-root strings from model and legacy record text."""
    if isinstance(value, dict):
        return {key: _browser_safe_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_browser_safe_value(item) for item in value]
    if isinstance(value, str):
        safe = value
        for root in sorted(allowed_data_roots(), key=len, reverse=True):
            safe = safe.replace(root, "[approved local storage]")
        return safe
    return value


def _public_job(job: dict) -> dict:
    allowed = {
        "job_id", "kind", "title", "status", "created_at", "started_at", "completed_at",
    }
    public = {key: value for key, value in job.items() if key in allowed}
    if job.get("status") == "completed":
        public["result"] = _browser_safe_value(job.get("result"))
    elif job.get("status") in {"failed", "interrupted"}:
        public["error"] = (
            "The application restarted before this job completed."
            if job.get("status") == "interrupted"
            else "The job failed. Check the local server log for diagnostics."
        )
    return public


def _write_case_summary(case_dir: str, client_name: str, review: dict, recent_file: str,
                        extraction_detail: str) -> str:
    """Persist a transparent, human-readable review artifact."""
    summary_path = resolve_within(case_dir, "CLIENT_FILE.md")
    lines = [
        f"# Matter: {client_name}",
        "",
        "> AI-generated working summary. Verify all facts, dates, and next steps.",
        "",
        f"**Last reviewed:** {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"**Most recent intake:** {recent_file}",
        f"**Content processing:** {extraction_detail}",
        "",
        "## Status summary",
        "",
        str(review.get("summary") or "The automated review did not produce a summary. Manual review is required."),
        "",
        "## Next steps",
        "",
    ]
    next_steps = review.get("next_steps") if isinstance(review.get("next_steps"), list) else []
    lines.extend(f"- {str(item)[:1000]}" for item in next_steps[:20])
    if not next_steps:
        lines.append("- Manual review required.")

    lines.extend(["", "## Required documents", ""])
    required = review.get("required_documents") if isinstance(review.get("required_documents"), dict) else {}
    lines.extend(f"- {str(name)[:300]} — {str(status)[:500]}" for name, status in list(required.items())[:50])
    if not required:
        lines.append("- None identified by the automated review.")

    lines.extend(["", "## Deadlines", ""])
    deadlines = review.get("deadlines") if isinstance(review.get("deadlines"), list) else []
    for deadline in deadlines[:20]:
        if isinstance(deadline, dict):
            lines.append(f"- {str(deadline.get('date', 'Unverified date'))[:100]} — "
                         f"{str(deadline.get('description', ''))[:800]}")
    if not deadlines:
        lines.append("- None identified. Confirm independently.")
    lines.append("")
    atomic_write_text(summary_path, "\n".join(lines))
    return summary_path


def _resolve_public_case_file(case_dir: str, rel_path: str, *, must_exist: bool = True) -> str:
    candidate = resolve_within(case_dir, rel_path, must_exist=must_exist)
    if candidate != os.path.realpath(case_dir):
        relative_parts = Path(os.path.relpath(candidate, case_dir)).parts
        if (path_is_sensitive(candidate, root=case_dir)
                or any(part.startswith(".") for part in relative_parts)):
            raise SecurityValidationError("Private matter runtime files are not available through the dashboard.")
    return candidate


def _extract_review_lines(file_path: str) -> tuple[str, str, list[str]]:
    extension = os.path.splitext(file_path)[1].lower()
    if extension not in REVIEWABLE_EXTENSIONS:
        return "manual_review_required", "In-app review is not available for this file type.", []
    try:
        extraction = extract_document_text(file_path)
        return extraction.status, extraction.detail, extraction.text.splitlines()[:5_000]
    except Exception as exc:  # noqa: BLE001 - untrusted parser boundary
        logger.warning("Document review extraction failed for %s: %s", os.path.basename(file_path), exc)
        return (
            "manual_review_required",
            "The document could not be extracted safely; open it in the system application.",
            [],
        )


def _document_review_payload(case_dir: str, rel_path: str) -> dict:
    """Return bounded extracted lines plus annotations without exposing local paths."""
    file_path = _resolve_public_case_file(case_dir, rel_path, must_exist=True)
    if not os.path.isfile(file_path):
        raise FileNotFoundError("Document not found.")
    normalized_rel = os.path.relpath(file_path, case_dir).replace(os.sep, "/")
    extraction_status, extraction_detail, raw_lines = _extract_review_lines(file_path)
    store = DocumentReviewStore(case_dir)
    notes = store.list_notes(normalized_rel)
    line_hashes = {
        index: hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:20]
        for index, text in enumerate(raw_lines, start=1)
    }
    public_notes = []
    for note in notes:
        public_notes.append({
            key: value for key, value in {
                "id": note.get("id"),
                "kind": note.get("kind"),
                "line_number": note.get("line_number"),
                "line_text": note.get("line_text"),
                "comment": note.get("comment"),
                "status": note.get("status"),
                "created_at": note.get("created_at"),
                "updated_at": note.get("updated_at"),
                "stale": line_hashes.get(note.get("line_number")) != note.get("line_hash"),
            }.items() if value is not None
        })
    return _browser_safe_value({
        "file": {
            "name": os.path.basename(file_path),
            "path": normalized_rel,
            "size": os.path.getsize(file_path),
            "modified_at": datetime.fromtimestamp(os.path.getmtime(file_path)).isoformat(),
        },
        "extraction": {
            "status": extraction_status,
            "detail": extraction_detail,
            "line_count": len(raw_lines),
            "truncated": len(raw_lines) >= 5_000,
        },
        "lines": [{"number": index, "text": text} for index, text in enumerate(raw_lines, start=1)],
        "notes": public_notes,
        "open_note_count": sum(note.get("status") != "resolved" for note in notes),
    })


def _queue_document_feedback(
    *, case: dict, slug: str, case_dir: str, normalized_rel: str,
    board: OfficeBoard | None = None,
) -> tuple[str, bool]:
    notes = DocumentReviewStore(case_dir).list_notes(normalized_rel, include_resolved=False)
    if not notes:
        raise SecurityValidationError("Add at least one open review note before queueing corrections.")
    file_name = os.path.basename(normalized_rel)
    review_key = "document_feedback:" + hashlib.sha256(
        f"{slug}:{normalized_rel}".encode("utf-8", errors="replace")
    ).hexdigest()[:20]
    board = board or OfficeBoard()
    existing = next((
        task for task in board.board.get("active_tasks", [])
        if isinstance(task.get("details"), dict)
        and task["details"].get("review_key") == review_key
        and task.get("status") in {"queued", "in_progress", "blocked"}
    ), None)
    if existing:
        return str(existing.get("id")), False
    task_id = board.post_task(
        f"Apply document feedback: {file_name}",
        "User",
        "Alix",
        "HIGH",
        details={
            "client_name": case.get("client_name"),
            "client_slug": slug,
            "file_path": normalized_rel,
            "work_type": "document_feedback",
            "review_key": review_key,
            "next_action": (
                "Read AIMAOS_REVIEW_NOTES.md, apply every open note to a new reviewed draft, "
                "and preserve the source document."
            ),
        },
    )
    return task_id, True


class AIMAOSUIHandler(SimpleHTTPRequestHandler):
    server_version = "AIMAOSBeta"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=os.path.join(AIMAOS_ROOT, "ui"), **kwargs)

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Permissions-Policy", "camera=(), geolocation=(), microphone=(self)")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
            "connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'none'; "
            "frame-ancestors 'none'; form-action 'self'",
        )
        super().end_headers()

    def log_message(self, fmt, *args):
        logger.info("%s - %s", self.client_address[0], fmt % args)

    @property
    def parsed_path(self):
        return urlparse(self.path)

    @property
    def config(self):
        return load_security_config()

    def _send_json(self, payload: dict, status: int = 200):
        body = json.dumps(payload, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _error(self, status: int, message: str, *, code: str = "request_error"):
        self._send_json({"status": "error", "error": {"code": code, "message": message}}, status)

    def _supplied_access_token(self):
        auth = self.headers.get("Authorization", "")
        if auth.lower().startswith("bearer "):
            return auth[7:].strip()
        return self.headers.get("X-AIMAOS-Token")

    def _authorized(self) -> bool:
        expected = os.environ.get("AIMAOS_UI_TOKEN")
        if token_matches(expected, self._supplied_access_token()):
            return True
        self._error(401, "An access token is required.", code="authentication_required")
        return False

    def _same_origin(self) -> bool:
        if self.headers.get("Sec-Fetch-Site") == "cross-site":
            return False
        origin = self.headers.get("Origin")
        if not origin:
            return True
        parsed = urlparse(origin)
        return parsed.scheme in {"http", "https"} and parsed.netloc == self.headers.get("Host")

    def _mutation_allowed(self) -> bool:
        if not self._authorized():
            return False
        if not self._same_origin():
            self._error(403, "Cross-origin mutations are not allowed.", code="origin_rejected")
            return False
        if not token_matches(CSRF_TOKEN, self.headers.get("X-AIMAOS-CSRF")):
            self._error(403, "The request is missing a valid CSRF token.", code="csrf_rejected")
            return False
        return True

    def _read_json(self) -> dict:
        content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            raise SecurityValidationError("Requests must use application/json.")
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise SecurityValidationError("Invalid Content-Length.") from exc
        max_upload = int(self.config.get("ui", {}).get("max_upload_mb", 25)) * 1024 * 1024
        if length <= 0 or length > max_upload * 2 + 1_000_000:
            raise SecurityValidationError("Request body is empty or too large.")
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SecurityValidationError("Malformed JSON request.") from exc
        if not isinstance(data, dict):
            raise SecurityValidationError("The JSON request must be an object.")
        return data

    def _case_record(self, slug: str) -> tuple[dict, str]:
        slug = validate_slug(slug, label="matter identifier")
        case = OfficeSQLite().get_case(slug)
        if not case:
            raise FileNotFoundError("Matter not found.")
        case_dir = require_allowed_path(case.get("path", ""))
        if not os.path.isdir(case_dir):
            raise FileNotFoundError("Matter storage is unavailable.")
        return case, case_dir

    def _send_file(self, path: str):
        filename = os.path.basename(path)
        header_filename = "".join(
            character if 32 <= ord(character) < 127 and character not in {'"', '\\'} else "_"
            for character in filename
        ) or "download"
        content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        size = os.path.getsize(path)
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(size))
        self.send_header("Content-Disposition", f'attachment; filename="{header_filename}"')
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        with open(path, "rb") as handle:
            while chunk := handle.read(64 * 1024):
                self.wfile.write(chunk)

    def do_GET(self):
        path = self.parsed_path.path
        if path in {"/", "/index.html"}:
            self.path = "/aimaos_ui.html"
            return super().do_GET()
        if not path.startswith("/api/"):
            return super().do_GET()
        if not self._authorized():
            return

        try:
            query = parse_qs(self.parsed_path.query)
            if path == "/api/bootstrap":
                cfg = self.config
                return self._send_json({
                    "status": "success",
                    "version": APP_VERSION,
                    "started_at": STARTED_AT,
                    "csrf_token": CSRF_TOKEN,
                    "setup_complete": _setup_complete(),
                    "developer_mode": developer_mode_enabled(cfg),
                    "native_open_enabled": bool(cfg.get("ui", {}).get("allow_native_open", True)),
                    "max_upload_mb": int(cfg.get("ui", {}).get("max_upload_mb", 25)),
                    "privacy": {
                        "raw_tool_logs": bool(cfg.get("privacy", {}).get("store_raw_tool_logs", False)),
                        "retention_days": int(cfg.get("privacy", {}).get("log_retention_days", 30)),
                    },
                })

            if path == "/api/status":
                board = OfficeBoard()
                roster = []
                for name, state in board.board.get("agent_statuses", {}).items():
                    roster.append({"name": name, "status": state})
                return self._send_json({
                    "status": "success",
                    "active_tasks": [_public_task(task) for task in board.board.get("active_tasks", [])],
                    "work_items": _browser_safe_value(build_workstation_items(board=board)),
                    "completed_task_count": len(board.board.get("completed_tasks", [])),
                    "agents": roster,
                    "daemon": _daemon_status(),
                    "jobs": [_public_job(job) for job in get_job_manager().list(limit=20)],
                })

            if path == "/api/cases":
                cases = [_public_case(case) for case in OfficeSQLite().list_all_cases()]
                return self._send_json({"status": "success", "cases": cases})

            if path == "/api/case_file":
                slug = query.get("slug", [""])[0]
                case, case_dir = self._case_record(slug)
                summary = "No matter summary has been generated yet."
                summary_path = resolve_within(case_dir, "CLIENT_FILE.md")
                if os.path.isfile(summary_path):
                    with open(summary_path, "r", encoding="utf-8", errors="replace") as handle:
                        summary = handle.read(250_000)
                files = []
                for root, dirs, names in os.walk(case_dir):
                    dirs[:] = [d for d in dirs if not d.startswith(".")]
                    for name in sorted(names):
                        if name.startswith("."):
                            continue
                        file_path = _resolve_public_case_file(case_dir, os.path.relpath(os.path.join(root, name), case_dir))
                        rel_path = os.path.relpath(file_path, case_dir)
                        files.append({
                            "name": name,
                            "path": rel_path,
                            "size": os.path.getsize(file_path),
                            "modified_at": datetime.fromtimestamp(os.path.getmtime(file_path)).isoformat(),
                        })
                        if len(files) >= 500:
                            break
                    if len(files) >= 500:
                        break
                return self._send_json({
                    "status": "success", "case": _public_case(case),
                    "summary_md": _browser_safe_value(summary), "files": files
                })

            if path == "/api/templates":
                return self._send_json({"status": "success", "templates": _template_catalog()})

            if path == "/api/jobs":
                job_id = query.get("id", [None])[0]
                if job_id:
                    job = get_job_manager().get(job_id)
                    if not job:
                        return self._error(404, "Job not found.", code="not_found")
                    return self._send_json({"status": "success", "job": _public_job(job)})
                jobs = [_public_job(job) for job in get_job_manager().list()]
                return self._send_json({"status": "success", "jobs": jobs})

            if path == "/api/files/download":
                slug = query.get("slug", [""])[0]
                rel_path = query.get("path", [""])[0]
                _case, case_dir = self._case_record(slug)
                file_path = _resolve_public_case_file(case_dir, rel_path, must_exist=True)
                if not os.path.isfile(file_path):
                    raise FileNotFoundError("File not found.")
                return self._send_file(file_path)

            if path == "/api/document_review":
                slug = query.get("slug", [""])[0]
                rel_path = query.get("path", [""])[0]
                _case, case_dir = self._case_record(slug)
                return self._send_json({
                    "status": "success",
                    **_document_review_payload(case_dir, rel_path),
                })

            if path == "/api/reports":
                report_roots = [
                    os.path.join(AIMAOS_ROOT, "Zoe-AI", "workspace", "diagnostics"),
                    os.path.join(AIMAOS_ROOT, "Zoe-AI", "workspace", "reports"),
                ]
                reports = []
                for report_root in report_roots:
                    if not os.path.isdir(report_root):
                        continue
                    for name in sorted(os.listdir(report_root), reverse=True)[:50]:
                        report_path = resolve_within(report_root, name)
                        if os.path.isfile(report_path):
                            reports.append({"name": name, "size": os.path.getsize(report_path)})
                return self._send_json({"status": "success", "reports": reports})

            return self._error(404, "API route not found.", code="not_found")
        except SecurityValidationError as exc:
            return self._error(400, str(exc), code="validation_error")
        except FileNotFoundError as exc:
            return self._error(404, str(exc), code="not_found")
        except Exception as exc:  # noqa: BLE001 - API boundary
            logger.exception("GET %s failed", path)
            return self._error(500, "The request could not be completed. Check the local server log.",
                               code="internal_error")

    def do_POST(self):
        path = self.parsed_path.path
        if not path.startswith("/api/"):
            return self._error(404, "Route not found.", code="not_found")
        if not self._mutation_allowed():
            return

        try:
            data = self._read_json()
            work_routes = {
                "/api/chat", "/api/upload", "/api/generate_doc",
                "/api/quick_action", "/api/work_item",
                "/api/document_review_note", "/api/document_review_submit",
                "/api/daemon/pause", "/api/daemon/resume", "/api/daemon/toggle",
            }
            if path in work_routes and not _setup_complete():
                return self._error(
                    409, "Setup is incomplete. Run the setup wizard before starting office work.",
                    code="setup_required",
                )
            if path in {"/api/daemon/pause", "/api/daemon/resume", "/api/daemon/toggle"}:
                status = _daemon_status()
                current_pause = status.get("pause_requested", False)
                if path == "/api/daemon/pause":
                    target_pause = True
                elif path == "/api/daemon/resume":
                    target_pause = False
                else:
                    target_pause = not current_pause

                _set_daemon_pause_request(target_pause)

                if not target_pause and not status.get("responsive"):
                    _start_daemon_process()

                message = (
                    "Pause requested. Agents will clock out as soon as the current task completes."
                    if target_pause
                    else "Office resumed. Agents are clocking in."
                )
                return self._send_json({
                    "status": "success",
                    "pause_requested": target_pause,
                    "message": message,
                    "daemon": _daemon_status(),
                })

            if path == "/api/chat":
                message = str(data.get("message", "")).strip()
                if not message or len(message) > 10_000:
                    raise SecurityValidationError("Message must be between 1 and 10,000 characters.")
                matter_slug = data.get("matter_slug")
                if matter_slug:
                    matter_slug = validate_slug(matter_slug, label="matter identifier")
                    self._case_record(matter_slug)
                    message = f"For matter [{matter_slug}]: {message}"

                def chat_job():
                    finn = load_agent("Finn", "FinnAgent")
                    return {"message": finn.process_user_message(message)}

                job_id = get_job_manager().submit("assistant", "Assistant request", chat_job)
                return self._send_json({"status": "accepted", "job_id": job_id}, 202)

            if path == "/api/upload":
                client_name = str(data.get("client_name", "")).strip()
                if not client_name or len(client_name) > 120:
                    raise SecurityValidationError("Matter name must be between 1 and 120 characters.")
                slug = normalize_slug(client_name, label="matter name")
                existing_case = OfficeSQLite().get_case(slug)
                if existing_case and existing_case.get("client_name", "").casefold() != client_name.casefold():
                    raise SecurityValidationError(
                        "That matter name conflicts with an existing matter. Use a more specific name."
                    )
                allowed = self.config.get("ui", {}).get("allowed_upload_extensions") or DEFAULT_UPLOAD_EXTENSIONS
                filename = sanitize_filename(str(data.get("file_name", "")), allowed_extensions=allowed)
                encoded = data.get("content_base64")
                if not isinstance(encoded, str):
                    # Compatibility for prior text-only API clients.
                    text_content = data.get("content")
                    if not isinstance(text_content, str):
                        raise SecurityValidationError("Upload content is missing.")
                    raw = text_content.encode("utf-8")
                else:
                    try:
                        raw = base64.b64decode(encoded, validate=True)
                    except (binascii.Error, ValueError) as exc:
                        raise SecurityValidationError("Upload content is not valid base64.") from exc
                max_size = int(self.config.get("ui", {}).get("max_upload_mb", 25)) * 1024 * 1024
                if not raw or len(raw) > max_size:
                    raise SecurityValidationError("Uploaded file is empty or exceeds the configured size limit.")
                validate_upload_content(filename, raw)

                matter_dir = resolve_within(_output_root(), slug)
                os.makedirs(matter_dir, exist_ok=True)
                saved_file = _unique_destination(matter_dir, filename)
                with open(saved_file, "xb") as handle:
                    handle.write(raw)
                if os.name == "posix":
                    os.chmod(saved_file, 0o600)
                OfficeSQLite().upsert_case(
                    slug, client_name, matter_dir, matter_type="Document Intake", category="general"
                )

                def ingest_job():
                    from core.case_agent import CaseAgent
                    existing_summary = "No prior summary."
                    summary_path = resolve_within(matter_dir, "CLIENT_FILE.md")
                    if os.path.isfile(summary_path):
                        with open(summary_path, "r", encoding="utf-8", errors="replace") as handle:
                            existing_summary = handle.read(250_000)
                    listing = []
                    for name in sorted(os.listdir(matter_dir)):
                        if not name.startswith("."):
                            listing.append(name)
                    extraction = extract_document_text(saved_file)
                    update = CaseAgent(matter_dir, client_name, category="general").review(
                        existing_summary, "\n".join(listing),
                        document_excerpt=extraction.text if extraction.status == "extracted" else None,
                    )
                    _write_case_summary(
                        matter_dir, client_name, update, os.path.basename(saved_file), extraction.detail
                    )
                    OfficeBoard().log_activity(
                        f"[Secure Intake] Reviewed a new file for matter '{slug}'."
                    )
                    return {
                        "matter_slug": slug,
                        "file_name": os.path.basename(saved_file),
                        "review_status": (
                            "completed" if update and extraction.status == "extracted"
                            else "manual_review_required"
                        ),
                        "extraction_status": extraction.status,
                    }

                job_id = get_job_manager().submit("intake", f"Review {filename}", ingest_job)
                return self._send_json({
                    "status": "accepted", "job_id": job_id, "matter_slug": slug,
                    "file_name": os.path.basename(saved_file),
                }, 202)

            if path == "/api/generate_doc":
                template_id = validate_slug(str(data.get("template", "")), label="template identifier")
                template = next((item for item in _template_catalog() if item["id"] == template_id), None)
                if not template:
                    raise SecurityValidationError("Unknown document template.")
                context = data.get("context")
                if not isinstance(context, dict) or len(context) > 100:
                    raise SecurityValidationError("Document context must be an object with at most 100 fields.")
                clean_context = {}
                for key, value in context.items():
                    if not isinstance(key, str) or len(key) > 80:
                        raise SecurityValidationError("Invalid document field name.")
                    rendered = str(value).strip()
                    if len(rendered) > 20_000:
                        raise SecurityValidationError(f"Field '{key}' is too long.")
                    clean_context[key] = rendered
                client_name = clean_context.get("client_name", "").strip()
                if not client_name:
                    raise SecurityValidationError("Client name is required.")
                slug = normalize_slug(client_name, label="client name")

                def document_job():
                    sys.path.insert(0, os.path.join(AIMAOS_ROOT, "Alix-AI"))
                    from business.document_engine import DocumentEngine
                    template_path = resolve_within(_templates_root(), template_id, "template.docx", must_exist=True)
                    matter_dir = resolve_within(_output_root(), slug)
                    os.makedirs(matter_dir, exist_ok=True)
                    output_name = sanitize_output_basename(
                        f"{client_name}_{template_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                    )
                    output_path = resolve_within(matter_dir, f"{output_name}.docx")
                    required = [field["name"] for field in template["fields"] if field.get("required")]
                    result = DocumentEngine(template_path).generate(
                        clean_context, output_path, required_fields=required
                    )
                    OfficeSQLite().upsert_case(
                        slug, client_name, matter_dir, matter_type=template["name"], category="documents"
                    )
                    OfficeBoard().log_activity(
                        f"[Document Studio] Generated draft '{os.path.basename(output_path)}' for {client_name}."
                    )
                    return {
                        "matter_slug": slug,
                        "file_name": os.path.basename(output_path),
                        "document_status": result.get("status"),
                        "issues": result.get("issues", {}),
                        "draft_notice": "Human review is required before filing, sending, or relying on this draft.",
                    }

                job_id = get_job_manager().submit("document", f"Generate {template['name']}", document_job)
                return self._send_json({"status": "accepted", "job_id": job_id}, 202)

            if path == "/api/quick_action":
                if str(data.get("action", "")) == "review_blockers":
                    report = run_daily_advancement_review(force=True)
                    return self._send_json({
                        "status": "success",
                        "message": "Priorities and blockers were refreshed.",
                        "review": report,
                    })
                actions = {
                    "audit_all": ("Comprehensive Office & Matter Security Audit", "Finn", "HIGH"),
                    "synthesize_skills": ("Review Operational Lessons", "Zoe", "NORMAL"),
                    "scan_drives": ("Approved Storage & Workspace Archival Scan", "Kai", "NORMAL"),
                }
                action = actions.get(str(data.get("action", "")))
                if not action:
                    raise SecurityValidationError("Unknown quick action.")
                task_id = OfficeBoard().post_task(action[0], "User", action[1], action[2])
                return self._send_json({"status": "success", "task_id": task_id})

            if path == "/api/work_item":
                task_id = str(data.get("task_id", "")).strip()
                if not task_id or len(task_id) > 120 or not all(
                    character.isalnum() or character in "_:-" for character in task_id
                ):
                    raise SecurityValidationError("Invalid work item identifier.")
                action = str(data.get("action", "")).strip()
                if action == "complete":
                    try:
                        complete_human_task(task_id)
                    except ValueError as exc:
                        raise SecurityValidationError(str(exc)) from exc
                    message = "Follow-up completed and removed from the open agenda."
                elif action == "snooze":
                    try:
                        snooze_human_task(task_id, str(data.get("due_date", "")))
                    except ValueError as exc:
                        raise SecurityValidationError(str(exc)) from exc
                    message = "Follow-up moved to the selected date."
                else:
                    raise SecurityValidationError("Unknown work item action.")
                return self._send_json({"status": "success", "message": message})

            if path == "/api/document_review_note":
                slug = validate_slug(str(data.get("slug", "")), label="matter identifier")
                rel_path = str(data.get("path", ""))
                _case, case_dir = self._case_record(slug)
                file_path = _resolve_public_case_file(case_dir, rel_path, must_exist=True)
                if not os.path.isfile(file_path):
                    raise FileNotFoundError("Document not found.")
                normalized_rel = os.path.relpath(file_path, case_dir).replace(os.sep, "/")
                action = str(data.get("action", "create")).lower()
                store = DocumentReviewStore(case_dir)
                if action == "create":
                    try:
                        line_number = int(data.get("line_number"))
                    except (TypeError, ValueError) as exc:
                        raise SecurityValidationError("Choose a document line before adding a note.") from exc
                    _status, _detail, lines = _extract_review_lines(file_path)
                    if not 1 <= line_number <= len(lines):
                        raise SecurityValidationError("The selected document line is unavailable.")
                    comment = str(data.get("comment", "")).strip()
                    if not comment or len(comment) > 4_000:
                        raise SecurityValidationError("Review comments must be between 1 and 4,000 characters.")
                    try:
                        note = store.add_note(
                            rel_path=normalized_rel,
                            line_number=line_number,
                            line_text=lines[line_number - 1],
                            comment=comment,
                            kind=str(data.get("kind", "correction")),
                        )
                    except ValueError as exc:
                        raise SecurityValidationError(str(exc)) from exc
                    message = "Review note saved and made available to the matter team."
                elif action in {"resolve", "reopen"}:
                    note_id = str(data.get("note_id", "")).strip()
                    if not re.fullmatch(r"note_[a-f0-9]{16}", note_id):
                        raise SecurityValidationError("Invalid review note identifier.")
                    try:
                        note = store.set_note_status(
                            rel_path=normalized_rel,
                            note_id=note_id,
                            status="resolved" if action == "resolve" else "open",
                        )
                    except ValueError as exc:
                        raise SecurityValidationError(str(exc)) from exc
                    message = "Review note updated."
                else:
                    raise SecurityValidationError("Unknown document review action.")
                OfficeBoard().log_activity(
                    f"[Document Review] Staff updated review notes for '{os.path.basename(file_path)}' in '{slug}'."
                )
                return self._send_json({"status": "success", "message": message, "note": note})

            if path == "/api/document_review_submit":
                slug = validate_slug(str(data.get("slug", "")), label="matter identifier")
                rel_path = str(data.get("path", ""))
                case, case_dir = self._case_record(slug)
                file_path = _resolve_public_case_file(case_dir, rel_path, must_exist=True)
                if not os.path.isfile(file_path):
                    raise FileNotFoundError("Document not found.")
                normalized_rel = os.path.relpath(file_path, case_dir).replace(os.sep, "/")
                task_id, created = _queue_document_feedback(
                    case=case, slug=slug, case_dir=case_dir, normalized_rel=normalized_rel,
                )
                return self._send_json({
                    "status": "success",
                    "task_id": task_id,
                    "message": (
                        "Document corrections were queued for Alix."
                        if created else "Document corrections are already in the office queue."
                    ),
                })

            if path == "/api/open_file":
                if not bool(self.config.get("ui", {}).get("allow_native_open", True)):
                    return self._error(403, "Opening native files is disabled.", code="feature_disabled")
                slug = validate_slug(str(data.get("slug", "")), label="matter identifier")
                rel_path = str(data.get("path", ""))
                _case, case_dir = self._case_record(slug)
                file_path = _resolve_public_case_file(case_dir, rel_path, must_exist=True)
                if not os.path.isfile(file_path):
                    raise SecurityValidationError("Only files can be opened in a system application.")
                allowed_extensions = {
                    str(item).lower() for item in (
                        self.config.get("ui", {}).get("allowed_upload_extensions")
                        or DEFAULT_UPLOAD_EXTENSIONS
                    )
                }
                if os.path.splitext(file_path)[1].lower() not in allowed_extensions:
                    raise SecurityValidationError("This file type cannot be opened from the dashboard.")
                if sys.platform == "darwin":
                    opener = ["open", file_path]
                elif os.name == "nt":
                    opener = ["cmd", "/c", "start", "", file_path]
                else:
                    native_opener = shutil.which("xdg-open")
                    if not native_opener:
                        return self._error(501, "No supported system file opener is installed.",
                                           code="feature_unavailable")
                    opener = [native_opener, file_path]
                subprocess.Popen(opener, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return self._send_json({"status": "success", "message": "Opened in the system application."})

            if path == "/api/voice_scribe":
                note = str(data.get("text", "")).strip()
                slug = validate_slug(str(data.get("matter_slug", "")), label="matter identifier")
                if not note or len(note) > 20_000:
                    raise SecurityValidationError("Note must be between 1 and 20,000 characters.")
                case, case_dir = self._case_record(slug)
                notes_path = resolve_within(case_dir, "MATTER_NOTES.md")
                with NOTES_LOCK:
                    existing_notes = "# Operator notes\n\n"
                    if os.path.isfile(notes_path):
                        if os.path.getsize(notes_path) > 2_000_000:
                            raise SecurityValidationError(
                                "The matter notes file has reached its beta size limit; archive it before adding notes."
                            )
                        with open(notes_path, "r", encoding="utf-8", errors="replace") as handle:
                            existing_notes = handle.read()
                    atomic_write_text(
                        notes_path,
                        existing_notes + f"## {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n{note}\n\n",
                    )
                from core.case_agent import CaseAgent
                agent = CaseAgent(case_dir, case.get("client_name", slug), category=case.get("category", "general"))
                agent.record_experience(f"User-approved dictated note: {note}", category="memory", confidence=0.9)
                return self._send_json({"status": "success", "message": "Note attached to the matter."})

            if path == "/api/clone_agent":
                if not developer_mode_enabled(self.config):
                    return self._error(403, "Agent creation is disabled outside developer mode.", code="feature_disabled")
                name = validate_agent_name(str(data.get("agent_name", "")))
                role = str(data.get("role", "")).strip()
                if not role or len(role) > 120:
                    raise SecurityValidationError("Role must be between 1 and 120 characters.")
                module = _load_module(
                    "aimaos_ui_rae_clone", os.path.join(AIMAOS_ROOT, "Rae-AI", "tools", "clone_agent.py")
                )
                result = str(module.execute(name, role))
                if result.startswith("Error:"):
                    raise SecurityValidationError(result.removeprefix("Error:").strip())
                return self._send_json({
                    "status": "success",
                    "message": f"Agent '{name}' was created. Restart AIMAOS to load it.",
                })

            return self._error(404, "API route not found.", code="not_found")
        except SecurityValidationError as exc:
            return self._error(400, str(exc), code="validation_error")
        except FileNotFoundError as exc:
            return self._error(404, str(exc), code="not_found")
        except Exception as exc:  # noqa: BLE001 - API boundary
            logger.exception("POST %s failed", path)
            return self._error(500, "The request could not be completed. Check the local server log.",
                               code="internal_error")

    def do_OPTIONS(self):
        self.send_response(405)
        self.send_header("Allow", "GET, POST")
        self.end_headers()


def _start_daemon_process() -> subprocess.Popen | None:
    if not _setup_complete():
        print("[AIMAOS] Setup is incomplete; the office daemon was not started.")
        return None
    status = _daemon_status()
    if status.get("responsive"):
        print("[AIMAOS] Office daemon is already responsive; not starting a duplicate.")
        return None
    return subprocess.Popen(
        [sys.executable, os.path.join(AIMAOS_ROOT, "run_office.py")],
        cwd=AIMAOS_ROOT,
        env={**os.environ, "AIMAOS_ROOT": AIMAOS_ROOT},
    )


def launch_aimaos_ui(port=8080, host="127.0.0.1", open_browser=True, start_daemon=True):
    cfg = load_security_config()
    allow_lan = bool(cfg.get("ui", {}).get("allow_lan", False))
    if not _is_loopback(host):
        if not allow_lan:
            raise RuntimeError("LAN binding is disabled. Set ui.allow_lan only after reviewing the security guide.")
        if not os.environ.get("AIMAOS_UI_TOKEN"):
            raise RuntimeError("AIMAOS_UI_TOKEN is required for a non-loopback binding.")
        if os.environ.get("AIMAOS_BEHIND_TLS_PROXY") != "1":
            raise RuntimeError(
                "Non-loopback access requires a TLS reverse proxy and AIMAOS_BEHIND_TLS_PROXY=1."
            )

    httpd = ThreadingHTTPServer((host, int(port)), AIMAOSUIHandler)
    httpd.daemon_threads = True
    try:
        daemon_process = _start_daemon_process() if start_daemon else None
    except Exception:
        httpd.server_close()
        raise
    display_host = "localhost" if _is_loopback(host) else host
    url = f"http://{display_host}:{port}"
    print("=" * 68)
    print(f"AIMAOS PUBLIC BETA {APP_VERSION}")
    print(f"Dashboard: {url}")
    print(f"Network boundary: {'loopback only' if _is_loopback(host) else 'authenticated LAN'}")
    print(f"Office daemon: {'managed by dashboard' if start_daemon else 'external / disabled'}")
    print("=" * 68)

    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            logger.warning("Could not open a browser automatically.")
    previous_sigterm = None
    if threading.current_thread() is threading.main_thread():
        previous_sigterm = signal.getsignal(signal.SIGTERM)

        def _stop_on_sigterm(_signum, _frame):
            raise KeyboardInterrupt

        signal.signal(signal.SIGTERM, _stop_on_sigterm)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[AIMAOS] Stopping dashboard and managed office daemon.")
    finally:
        if previous_sigterm is not None:
            signal.signal(signal.SIGTERM, previous_sigterm)
        httpd.server_close()
        if daemon_process and daemon_process.poll() is None:
            daemon_process.terminate()
            try:
                daemon_process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                daemon_process.kill()


def main(argv=None):
    if os.name == "posix":
        os.umask(0o077)
    cfg = load_security_config().get("ui", {})
    parser = argparse.ArgumentParser(description="AIMAOS local-first dashboard")
    parser.add_argument("--host", default=cfg.get("host", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(cfg.get("port", 8080)))
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--no-daemon", action="store_true")
    args = parser.parse_args(argv)
    launch_aimaos_ui(
        port=args.port,
        host=args.host,
        open_browser=not args.no_browser,
        start_daemon=not args.no_daemon,
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    main()

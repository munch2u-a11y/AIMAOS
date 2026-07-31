"""Kai's record-keeping core: creates and organizes client/case directories
and maintains each one's persistent case file (running summary, next
steps, required-document checklist, activity log).

Kai decides the organizational scheme, not this module — `category` is
whatever folder label the calling agent's own judgment settles on (by
matter/case type, by branch, whatever fits how this particular office's
work is actually organized; seed beliefs are where that judgment lives and
evolves, not hardcoded logic here). This module just makes the chosen
scheme durable: it creates the directory, and a small index keeps every
client findable by name regardless of which category they ended up under.

State lives in a JSON sidecar per client (`.client_file_state.json`); the
markdown view (`CLIENT_FILE.md`) is regenerated from it in full on every
write rather than parsed/patched as text — the one thing this module must
never get subtly wrong is losing or corrupting a case's own record.

OUTPUT_ROOT stays under Alix-AI/workspace/output — that's already the
office's de facto shared archive (Kai's own check_duplicates.py already
scans it), not really "Alix's" despite the historical path.
"""
import os

def _find_aimaos_root():
    p = os.path.dirname(os.path.abspath(__file__))
    while p != os.path.dirname(p) and not os.path.exists(os.path.join(p, "aimaos_config.yaml")):
        p = os.path.dirname(p)
    return p
AIMAOS_ROOT = os.environ.get("AIMAOS_ROOT") or _find_aimaos_root()
import json
import shutil
from datetime import datetime
from core.atomic_io import atomic_write_json, atomic_write_text
from core.security import normalize_slug, require_allowed_path, resolve_within

OUTPUT_ROOT = os.path.join(AIMAOS_ROOT, "Alix-AI/workspace/output")
INDEX_PATH = os.path.join(OUTPUT_ROOT, ".client_index.json")
DISPATCHED_STATUSES = ("dispatched", "filed", "on_file", "completed", "done")
_RECORD_INTERNAL_NAMES = {"CLIENT_FILE.md", ".client_file_state.json"}


def _load_index():
    if os.path.exists(INDEX_PATH):
        with open(INDEX_PATH) as f:
            return json.load(f)
    return {}


def _save_index(index):
    os.makedirs(OUTPUT_ROOT, exist_ok=True)
    atomic_write_json(INDEX_PATH, index)


def _slug(name):
    return normalize_slug(name, label="client name")


def client_exists(client_name):
    """Non-creating existence check — unlike resolve_client_dir, this never
    creates a directory or index entry. Use before filing anything for a
    client asserted to already have a case."""
    return _slug(client_name) in _load_index()


def resolve_client_dir(client_name, category=None):
    """Finds a client's existing directory regardless of category; creates
    one under `category` (or the output root if none given) if it doesn't
    exist yet."""
    slug = _slug(client_name)
    index = _load_index()
    if slug in index:
        path = require_allowed_path(index[slug], must_exist=False)
        os.makedirs(path, exist_ok=True)
        return path

    category_slug = normalize_slug(category, label="category") if category else None
    path = resolve_within(OUTPUT_ROOT, category_slug, slug) if category_slug else resolve_within(OUTPUT_ROOT, slug)
    os.makedirs(path, exist_ok=True)
    index[slug] = path
    _save_index(index)
    return path


def _state_path(client_name, category=None):
    return os.path.join(resolve_client_dir(client_name, category), ".client_file_state.json")


def _md_path(client_name, category=None):
    return os.path.join(resolve_client_dir(client_name, category), "CLIENT_FILE.md")


def _load_state(client_name):
    path = _state_path(client_name)
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return None


def _render_markdown(state):
    lines = [
        f"# Client File: {state['client_name']}",
        "",
        f"**Matter:** {state.get('matter_type') or 'Unspecified'}",
        f"**Case Number:** {state.get('case_number') or 'Not yet assigned'}",
        f"**State:** {state.get('state') or 'open'}",
        f"**Category:** {state.get('category') or 'Uncategorized'}",
        f"**Opened:** {state['opened']}",
        f"**Last Updated:** {state['last_updated']}",
        f"**Last Reviewed:** {state.get('last_reviewed_at') or 'Never'}",
        f"**Preferred Contact Channel:** {state.get('preferred_channel') or 'Not specified (email only channel wired today)'}",
        "",
        "## Status Summary",
        "",
        state.get("summary") or "*No summary yet.*",
        "",
        "## Next Steps",
        "",
    ]
    steps = state.get("next_steps") or []
    lines += [f"- {s}" for s in steps] if steps else ["*None recorded.*"]

    lines += ["", "## Required Documents", ""]
    docs = state.get("required_documents") or {}
    if docs:
        for name, info in docs.items():
            checked = "x" if info.get("status") in DISPATCHED_STATUSES else " "
            path_note = f" — {info['path']}" if info.get("path") else ""
            lines.append(f"- [{checked}] {name} — {info.get('status', 'not_started')}{path_note}")
    else:
        lines.append("*None recorded.*")

    lines += ["", "## Activity Log", ""]
    log = state.get("activity_log") or []
    if log:
        lines += [f"- {e['timestamp']} — {e['entry']}" for e in log]
    else:
        lines.append("*No activity yet.*")
    lines.append("")
    return "\n".join(lines)


import sys
sys.path.insert(0, AIMAOS_ROOT)
from core.db.office_sqlite import OfficeSQLite

def _save_state(client_name, state):
    state["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    path = resolve_client_dir(client_name)
    atomic_write_json(_state_path(client_name), state)
    atomic_write_text(_md_path(client_name), _render_markdown(state))
    try:
        db = OfficeSQLite()
        db.upsert_case(
            client_slug=_slug(client_name),
            client_name=state.get("client_name", client_name),
            path=path,
            matter_type=state.get("matter_type", "Legal Matter"),
            category=state.get("category", ""),
            status=state.get("state", "open"),
            case_number=state.get("case_number")
        )
    except Exception as e:
        pass



def create_case_file(client_name, matter_type, category=None, case_number=None):
    resolve_client_dir(client_name, category)  # ensures directory + index entry exist
    existing = _load_state(client_name)
    if existing:
        return existing, False
    state = {
        "client_name": client_name,
        "matter_type": matter_type,
        "category": category,
        "case_number": case_number,
        "opened": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "state": "open",
        "summary": "",
        "next_steps": [],
        "required_documents": {},
        "activity_log": [],
        "last_reviewed_at": None,
        "preferred_channel": None,
    }
    _save_state(client_name, state)
    return state, True


def log_entry(client_name, entry):
    state = _load_state(client_name)
    if state is None:
        return None
    state.setdefault("activity_log", []).append({
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "entry": entry,
    })
    _save_state(client_name, state)
    return state


def update_status(client_name, summary=None, next_steps=None, required_documents=None,
                  preferred_channel=None, state_label=None):
    state = _load_state(client_name)
    if state is None:
        return None
    if summary is not None:
        state["summary"] = summary
    if next_steps is not None:
        state["next_steps"] = list(next_steps)
    if required_documents is not None:
        docs = state.setdefault("required_documents", {})
        for name, status in required_documents.items():
            docs.setdefault(name, {})["status"] = status
    if preferred_channel is not None:
        state["preferred_channel"] = preferred_channel
    if state_label is not None:
        state["state"] = state_label
    _save_state(client_name, state)
    return state


def mark_document_dispatched(client_name, document_name, path):
    """Called automatically by dispatch_document.py (Alix) so the checklist
    and activity log stay current without depending on any agent
    remembering a separate cross-agent request."""
    state = _load_state(client_name)
    if state is None:
        state, _ = create_case_file(client_name, matter_type="Unspecified")
    docs = state.setdefault("required_documents", {})
    docs[document_name] = {"status": "dispatched", "path": path}
    state.setdefault("activity_log", []).append({
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "entry": f"Dispatched {document_name} -> {path}",
    })
    _save_state(client_name, state)
    return state


def get_preferred_channel(client_name):
    state = _load_state(client_name)
    return state.get("preferred_channel") if state else None


def get_markdown(client_name):
    path = _md_path(client_name)
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return f.read()


def mark_reviewed(client_name):
    """Called after a case-agent review actually completes, so staleness
    checks compare against when the case was last *reviewed*, not just last
    written to (dispatches and log entries update the record without a
    review having happened)."""
    state = _load_state(client_name)
    if state is None:
        return None
    state["last_reviewed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    _save_state(client_name, state)
    return state


def move_client_dir(client_name, new_category):
    """Physically relocates a client's whole directory tree under a new
    category (e.g. closing a case into a 'closed' branch, or correcting
    drift found by audit_records) and keeps every record of where it lives
    in sync: the shared index, the state's own `category` field (so
    CLIENT_FILE.md's rendered Category line never disagrees with the real
    path -- the same class of drift this function exists to fix), and an
    activity-log entry of the move itself. shutil.move carries the whole
    tree along as one unit, including the case-agent's own embedded mRAG
    store (.case_agent/), so nothing needs separate handling for it.

    Don't call this while a review of the same case may be in flight --
    client_file.py has no locking, and a move racing a review's own
    directory walk/writes is a real (if narrow) hazard."""
    slug = _slug(client_name)
    index = _load_index()
    if slug not in index:
        return None
    old_path = require_allowed_path(index[slug])
    if not os.path.isdir(old_path):
        return None

    new_category = normalize_slug(new_category, label="category")
    new_path = resolve_within(OUTPUT_ROOT, new_category, slug)
    if os.path.abspath(new_path) == os.path.abspath(old_path):
        return old_path

    os.makedirs(os.path.dirname(new_path), exist_ok=True)
    if os.path.exists(new_path):
        raise FileExistsError(f"Move target already exists: {new_path}")
    shutil.move(old_path, new_path)

    index[slug] = new_path
    _save_index(index)

    state = _load_state(client_name)
    if state is not None:
        old_category = state.get("category")
        state["category"] = new_category
        state.setdefault("activity_log", []).append({
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "entry": f"Moved from category '{old_category}' to '{new_category}' "
                     f"({old_path} -> {new_path}).",
        })
        _save_state(client_name, state)
    return new_path


def audit_records():
    """Reports (never silently fixes) discrepancies between the index and
    reality, so Kai's own judgment decides any correction via
    move_client_dir -- the same way it decides categories for new cases.
    A mechanical auto-fix would be actively dangerous here: a client whose
    real files only exist at a stale/off-scheme path has no safe automatic
    destination (which category fits them is exactly the kind of call this
    project deliberately never hardcodes), so blindly rewriting the index
    to "the canonical spot" would just orphan real data instead of moving
    it.

    Returns a list of {client_name, path, issue} findings. issue is one of:
      "missing" - indexed path doesn't exist on disk at all
      "no_state" - path exists but has no .client_file_state.json
      "off_root" - path exists and is valid, but sits outside OUTPUT_ROOT
                   (the literal, real drift signature this was built for)
    """
    findings = []
    index = _load_index()
    for slug, path in index.items():
        state_path = os.path.join(path, ".client_file_state.json")
        if not os.path.isdir(path):
            findings.append({"client_name": slug, "path": path, "issue": "missing"})
            continue
        if not os.path.exists(state_path):
            findings.append({"client_name": slug, "path": path, "issue": "no_state"})
            continue
        try:
            with open(state_path) as f:
                state = json.load(f)
            client_name = state.get("client_name", slug)
        except Exception:
            client_name = slug
        real = os.path.realpath(path)
        if not real.startswith(os.path.realpath(OUTPUT_ROOT) + os.sep):
            findings.append({"client_name": client_name, "path": path, "issue": "off_root"})
    return findings


def _latest_case_file_mtime(case_dir):
    """Newest modification time among the case's own files — excludes the
    record-keeping internals (CLIENT_FILE.md, its JSON state, and the
    case-agent's own belief store) so dispatches/reviews writing to those
    don't make a case look freshly-worked-on to itself."""
    latest = None
    for root, dirs, files in os.walk(case_dir):
        dirs[:] = [d for d in dirs if d != ".case_agent" and d != "__pycache__"]
        for f in files:
            if f in _RECORD_INTERNAL_NAMES:
                continue
            mtime = os.path.getmtime(os.path.join(root, f))
            if latest is None or mtime > latest:
                latest = mtime
    return latest


def list_stale_clients():
    """Clients whose directory has case files newer than their last review
    (or that have never been reviewed at all) — what Kai should check when
    doing its own housekeeping pass, rather than reviewing every case every
    time regardless of whether anything actually changed."""
    index = _load_index()
    stale = []
    for slug, path in index.items():
        state = None
        state_path = os.path.join(path, ".client_file_state.json")
        if os.path.exists(state_path):
            with open(state_path) as f:
                state = json.load(f)
        if state is None:
            continue
        client_name = state["client_name"]
        latest_mtime = _latest_case_file_mtime(path)
        if latest_mtime is None:
            continue  # no actual case files yet, nothing to review
        last_reviewed = state.get("last_reviewed_at")
        if last_reviewed is None:
            stale.append({"client_name": client_name, "reason": "never reviewed"})
            continue
        reviewed_ts = datetime.strptime(last_reviewed, "%Y-%m-%d %H:%M").timestamp()
        if latest_mtime > reviewed_ts:
            stale.append({"client_name": client_name, "reason": "files changed since last review"})
    return stale

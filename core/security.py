"""Security primitives shared by the public-beta API and agent tools.

The public beta is deliberately local-first.  All filesystem access is
resolved against explicit roots, user-controlled names never become paths,
and developer capabilities stay disabled unless the operator opts in.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import yaml


def _find_aimaos_root() -> str:
    path = Path(__file__).resolve()
    for parent in (path.parent, *path.parents):
        if (parent / "aimaos_config.yaml").exists():
            return str(parent)
    return str(path.parents[1])


AIMAOS_ROOT = os.environ.get("AIMAOS_ROOT") or _find_aimaos_root()
CONFIG_PATH = os.path.join(AIMAOS_ROOT, "aimaos_config.yaml")

SAFE_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,79}$")
SAFE_AGENT_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,31}$")
SAFE_TOOL_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")

DEFAULT_UPLOAD_EXTENSIONS = {
    ".txt", ".md", ".csv", ".json", ".yaml", ".yml", ".rtf",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx",
    ".png", ".jpg", ".jpeg", ".tif", ".tiff",
    ".wav", ".mp3", ".m4a", ".webm",
}

SENSITIVE_PATH_COMPONENTS = {
    ".git", ".venv", "venv", "env", "__pycache__", "comms", ".memory",
    "mrag_data", ".case_agent", ".sessions", "tool_logs", "task_logs",
}
SENSITIVE_FILENAMES = {".env", "credentials.env", "secrets.yaml"}


class SecurityValidationError(ValueError):
    """Raised when untrusted input cannot be safely normalized."""


def load_security_config() -> dict:
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as handle:
            return yaml.safe_load(handle) or {}
    except (OSError, yaml.YAMLError):
        return {}


def normalize_slug(value: str, *, label: str = "identifier") -> str:
    value = (value or "").strip().lower()
    value = re.sub(r"[^a-z0-9_-]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_-")
    if not value or not SAFE_SLUG_RE.fullmatch(value):
        raise SecurityValidationError(f"Invalid {label}.")
    return value


def validate_slug(value: str, *, label: str = "identifier") -> str:
    value = (value or "").strip().lower()
    if not SAFE_SLUG_RE.fullmatch(value):
        raise SecurityValidationError(f"Invalid {label}.")
    return value


def validate_agent_name(value: str) -> str:
    value = (value or "").strip()
    if not SAFE_AGENT_RE.fullmatch(value):
        raise SecurityValidationError(
            "Agent names must start with a letter and contain only letters, numbers, or underscores."
        )
    return value[0].upper() + value[1:]


def validate_tool_name(value: str, *, label: str = "tool name") -> str:
    value = (value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if not SAFE_TOOL_RE.fullmatch(value):
        raise SecurityValidationError(f"Invalid {label}.")
    return value


def sanitize_filename(filename: str, *, allowed_extensions: Iterable[str] | None = None) -> str:
    """Return a display-preserving filename that cannot contain a path."""
    raw = os.path.basename((filename or "").replace("\\", "/")).strip()
    stem, extension = os.path.splitext(raw)
    extension = extension.lower()
    allowed = {item.lower() for item in (allowed_extensions or DEFAULT_UPLOAD_EXTENSIONS)}
    if extension not in allowed:
        raise SecurityValidationError(f"File type '{extension or '(none)'}' is not allowed.")
    stem = re.sub(r"[^A-Za-z0-9._ -]+", "_", stem)
    stem = re.sub(r"\s+", " ", stem).strip(" ._")[:100]
    if not stem:
        stem = "upload"
    return f"{stem}{extension}"


def sanitize_output_basename(value: str, *, fallback: str = "document") -> str:
    value = os.path.basename((value or "").replace("\\", "/"))
    value = re.sub(r"[^A-Za-z0-9._ -]+", "_", value)
    value = re.sub(r"\s+", "_", value).strip("._-")[:120]
    return value or fallback


def resolve_within(root: str, *parts: str, must_exist: bool = False) -> str:
    """Resolve *parts under root and reject traversal, prefix tricks and symlinks."""
    root_real = os.path.realpath(os.path.abspath(root))
    candidate = os.path.realpath(os.path.abspath(os.path.join(root_real, *parts)))
    try:
        inside = os.path.commonpath([root_real, candidate]) == root_real
    except ValueError:
        inside = False
    if not inside:
        raise SecurityValidationError("Requested path is outside the allowed workspace.")
    if must_exist and not os.path.exists(candidate):
        raise FileNotFoundError(candidate)
    return candidate


def is_within_any(path: str, roots: Sequence[str]) -> bool:
    candidate = os.path.realpath(os.path.abspath(path))
    for root in roots:
        root_real = os.path.realpath(os.path.abspath(root))
        try:
            if os.path.commonpath([root_real, candidate]) == root_real:
                return True
        except ValueError:
            continue
    return False


def path_is_sensitive(path: str, *, root: str | None = None) -> bool:
    candidate = os.path.realpath(os.path.abspath(path))
    relative = os.path.relpath(candidate, root) if root else candidate
    parts = Path(relative).parts
    for part in parts:
        lowered = part.lower()
        if lowered in SENSITIVE_PATH_COMPONENTS or lowered in SENSITIVE_FILENAMES:
            return True
        if lowered.startswith(".env.") or lowered.endswith((".pem", ".key")):
            return True
    return False


def allowed_data_roots(config: Mapping | None = None) -> list[str]:
    """Roots agents and the UI may inspect.

    The application tree is included for templates and generated workspaces.
    Additional document roots must be configured explicitly; the user's whole
    home directory is never an implicit capability.
    """
    cfg = dict(config or load_security_config())
    roots = [AIMAOS_ROOT]
    for value in cfg.get("storage", {}).get("allowed_roots", []) or []:
        if not isinstance(value, str) or not value.strip():
            continue
        expanded = os.path.abspath(os.path.expanduser(value.strip()))
        if os.path.exists(expanded):
            roots.append(expanded)
    unique = []
    for root in roots:
        resolved = os.path.realpath(root)
        if resolved not in unique:
            unique.append(resolved)
    return unique


def require_allowed_path(path: str, config: Mapping | None = None, *, must_exist: bool = True) -> str:
    candidate = os.path.realpath(os.path.abspath(os.path.expanduser(path)))
    if not is_within_any(candidate, allowed_data_roots(config)):
        raise SecurityValidationError("Path is not inside an approved AIMAOS data root.")
    matching_root = next((root for root in allowed_data_roots(config)
                          if is_within_any(candidate, [root])), None)
    if matching_root and candidate != matching_root and path_is_sensitive(candidate, root=matching_root):
        raise SecurityValidationError("Sensitive runtime and credential paths are not available to agents.")
    if must_exist and not os.path.exists(candidate):
        raise FileNotFoundError(candidate)
    return candidate


def developer_mode_enabled(config: Mapping | None = None) -> bool:
    cfg = dict(config or load_security_config())
    return bool(cfg.get("ui", {}).get("developer_mode", False))


def shell_tools_enabled(config: Mapping | None = None) -> bool:
    cfg = dict(config or load_security_config())
    return developer_mode_enabled(cfg) and bool(cfg.get("security", {}).get("allow_shell_tools", False))


def tool_execution_policy(tool_name: str, arguments: Mapping | None = None,
                          config: Mapping | None = None) -> tuple[bool, str | None]:
    """Return whether an agent tool call is allowed by the beta policy.

    Read-only/local creation work remains available. External mutations and
    self-modifying capabilities are explicit operator opt-ins.
    """
    cfg = dict(config or load_security_config())
    args = dict(arguments or {})
    security = cfg.get("security", {})
    disabled = set(security.get("disabled_tools", []) or [])
    if tool_name in disabled:
        return False, f"Tool '{tool_name}' is disabled by the office security policy."

    developer_tools = {"clone_agent", "design_tool_subagent", "install_catalog_tool", "run_script"}
    if tool_name in developer_tools and not developer_mode_enabled(cfg):
        return False, f"Tool '{tool_name}' is available only in developer mode."

    network_tools = {
        "google_calendar", "manage_calendar", "web_search", "web_fetch", "rss_feed_read",
        "send_email", "reply_email", "commandeer_channel",
    }
    if tool_name in network_tools and not bool(security.get("allow_network_tools", False)):
        return False, (
            f"Network tool '{tool_name}' is disabled. An administrator must explicitly enable "
            "security.allow_network_tools after reviewing what data may leave the device."
        )

    external_mutation = False
    if tool_name in {"commandeer_channel", "send_email", "reply_email"}:
        external_mutation = True
    elif tool_name == "dispatch_document" and args.get("recipient_email"):
        external_mutation = True
    elif tool_name in {"google_calendar", "manage_calendar"}:
        external_mutation = args.get("action") in {"create_event", "update_event", "delete_event"}

    if external_mutation and not bool(security.get("allow_external_mutations", False)):
        return False, (
            f"External action '{tool_name}' is disabled. An administrator must explicitly enable "
            "security.allow_external_mutations after configuring review procedures."
        )
    input_path_keys = {
        "path", "file_path", "image_path", "audio_path", "drive_path", "directory",
        "source_path", "input_path", "template_path",
    }
    output_path_keys = {"output_path", "output_dir", "destination_path", "destination_dir"}
    list_path_keys = {"source_files", "input_files", "file_paths"}
    for key, value in args.items():
        values = value if key in list_path_keys and isinstance(value, list) else [value]
        if key not in input_path_keys | output_path_keys | list_path_keys:
            continue
        for path_value in values:
            if not isinstance(path_value, str) or not path_value.strip():
                continue
            try:
                require_allowed_path(
                    path_value,
                    cfg,
                    must_exist=key not in output_path_keys,
                )
            except (SecurityValidationError, FileNotFoundError):
                return False, f"Tool argument '{key}' is outside approved storage or unavailable."
    return True, None


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def token_matches(expected: str | None, supplied: str | None) -> bool:
    if not expected:
        return True
    return bool(supplied) and hmac.compare_digest(expected, supplied)


def content_digest(content: bytes | str) -> str:
    if isinstance(content, str):
        content = content.encode("utf-8", errors="replace")
    return hashlib.sha256(content).hexdigest()

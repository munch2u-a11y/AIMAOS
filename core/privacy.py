"""Local privacy defaults for logs and learned operational memories."""
from __future__ import annotations

import hashlib
import os
import re
from datetime import datetime, timedelta

from core.security import load_security_config


_SENSITIVE_PATTERNS = (
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[REDACTED SSN]"),
    (re.compile(r"\b(?:\d[ -]*?){13,19}\b"), "[REDACTED NUMBER]"),
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "[REDACTED EMAIL]"),
)


def redact_sensitive(text: object) -> str:
    value = str(text)
    for pattern, replacement in _SENSITIVE_PATTERNS:
        value = pattern.sub(replacement, value)
    return value


def raw_tool_logs_enabled() -> bool:
    return bool(load_security_config().get("privacy", {}).get("store_raw_tool_logs", False))


def privacy_safe_tool_record(raw_output: object) -> dict:
    raw = str(raw_output)
    record = {
        "output_sha256": hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest(),
        "output_chars": len(raw),
    }
    if raw_tool_logs_enabled():
        record["raw_output"] = redact_sensitive(raw)
    else:
        record["raw_output"] = "[disabled by privacy.store_raw_tool_logs policy]"
    return record


def prune_runtime_records(aimaos_root: str) -> dict:
    cfg = load_security_config().get("privacy", {})
    retention_days = max(1, int(cfg.get("log_retention_days", 30)))
    cutoff = datetime.now() - timedelta(days=retention_days)
    removed = {"tool_logs": 0, "read_messages": 0}

    for root, _dirs, files in os.walk(aimaos_root):
        normalized = root.replace("\\", "/")
        for filename in files:
            kind = None
            if "/tool_logs" in normalized and filename.endswith(".json"):
                kind = "tool_logs"
            elif filename.endswith(".read") and "/comms/" in normalized:
                kind = "read_messages"
            if not kind:
                continue
            path = os.path.join(root, filename)
            try:
                if datetime.fromtimestamp(os.path.getmtime(path)) < cutoff:
                    os.remove(path)
                    removed[kind] += 1
            except OSError:
                continue
    return removed

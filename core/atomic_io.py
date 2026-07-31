"""Crash-resistant local writes with private file permissions."""
from __future__ import annotations

import json
import os
import tempfile


def atomic_write_text(path: str, content: str, *, mode: int = 0o600) -> None:
    directory = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(directory, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=directory, prefix=".aimaos-", delete=False
        ) as handle:
            temporary = handle.name
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        if os.name == "posix":
            os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            try:
                os.unlink(temporary)
            except OSError:
                pass


def atomic_write_json(path: str, payload, *, mode: int = 0o600) -> None:
    atomic_write_text(path, json.dumps(payload, indent=2, default=str), mode=mode)

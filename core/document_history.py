"""Crash-safe revision history and 1-click rollback store for AIMAOS matter documents."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
import uuid
from datetime import datetime
from pathlib import Path

from core.atomic_io import atomic_write_text, atomic_write_json
from core.security import resolve_within


class DocumentHistoryStore:
    """Manages automatic revision snapshots and rollbacks for documents in a case directory."""

    def __init__(self, case_dir: str):
        self.case_dir = os.path.abspath(case_dir)
        self.history_dir = os.path.join(self.case_dir, ".aimaos_history")
        os.makedirs(self.history_dir, exist_ok=True)

    def _history_entry_dir(self, rel_path: str) -> str:
        """Return private directory path for a specific file's revision snapshots."""
        safe_rel = rel_path.strip("/").replace("/", "__")
        path_hash = hashlib.sha256(rel_path.encode("utf-8")).hexdigest()[:12]
        entry_dir = os.path.join(self.history_dir, f"{safe_rel}_{path_hash}")
        os.makedirs(entry_dir, exist_ok=True)
        return entry_dir

    def _manifest_path(self, rel_path: str) -> str:
        return os.path.join(self._history_entry_dir(rel_path), "revisions.json")

    def list_revisions(self, rel_path: str) -> list[dict]:
        """Return ordered list of historical revisions for a document (newest first)."""
        manifest_file = self._manifest_path(rel_path)
        if not os.path.isfile(manifest_file):
            return []
        try:
            with open(manifest_file, "r", encoding="utf-8") as f:
                revisions = json.load(f)
                return sorted(revisions, key=lambda r: r.get("timestamp", ""), reverse=True)
        except Exception:
            return []

    def create_snapshot(
        self, rel_path: str, author: str = "User", comment: str = "Automatic revision snapshot"
    ) -> dict | None:
        """Create a snapshot of the current document state prior to modification."""
        full_path = resolve_within(self.case_dir, rel_path)
        if not os.path.isfile(full_path):
            return None

        entry_dir = self._history_entry_dir(rel_path)
        ext = os.path.splitext(full_path)[1]
        rev_id = f"rev_{int(time.time())}_{uuid.uuid4().hex[:6]}"
        snapshot_filename = f"{rev_id}{ext}"
        snapshot_path = os.path.join(entry_dir, snapshot_filename)

        # Copy document binary/text cleanly
        shutil.copy2(full_path, snapshot_path)

        with open(full_path, "rb") as f:
            file_hash = hashlib.sha256(f.read()).hexdigest()

        revision = {
            "revision_id": rev_id,
            "snapshot_file": snapshot_filename,
            "timestamp": datetime.now().isoformat(),
            "author": author,
            "comment": comment,
            "sha256": file_hash,
            "size": os.path.getsize(full_path),
        }

        revisions = self.list_revisions(rel_path)
        # Check if identical hash snapshot already exists at top
        if revisions and revisions[0].get("sha256") == file_hash:
            return revisions[0]

        revisions.insert(0, revision)
        atomic_write_json(self._manifest_path(rel_path), revisions)
        return revision

    def rollback_revision(self, rel_path: str, revision_id: str, author: str = "User") -> dict:
        """Restore document content to specified historical revision snapshot."""
        full_path = resolve_within(self.case_dir, rel_path)
        if not os.path.isfile(full_path):
            raise FileNotFoundError(f"Target document '{rel_path}' does not exist.")

        revisions = self.list_revisions(rel_path)
        target_rev = next((r for r in revisions if r.get("revision_id") == revision_id), None)
        if not target_rev:
            raise ValueError(f"Revision '{revision_id}' not found for '{rel_path}'.")

        entry_dir = self._history_entry_dir(rel_path)
        snapshot_path = os.path.join(entry_dir, target_rev["snapshot_file"])
        if not os.path.isfile(snapshot_path):
            raise FileNotFoundError(f"Snapshot file for '{revision_id}' missing.")

        # 1. Take safety snapshot of current state before rollback
        self.create_snapshot(rel_path, author=author, comment=f"Pre-rollback backup before restoring {revision_id}")

        # 2. Restore file in-place
        shutil.copy2(snapshot_path, full_path)

        # 3. Create a snapshot representing the restored state
        new_rev = self.create_snapshot(rel_path, author=author, comment=f"Rolled back to revision {revision_id}")
        return new_rev or target_rev

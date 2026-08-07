"""Tests for AIMAOS Document Revision History and 1-Click Rollback."""
from __future__ import annotations

import os
import tempfile
import unittest

from core.document_history import DocumentHistoryStore
from core.db.office_sqlite import OfficeSQLite


class TestDocumentHistory(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.case_dir = os.path.join(self.temp_dir.name, "Casale")
        os.makedirs(self.case_dir, exist_ok=True)
        self.sample_doc = os.path.join(self.case_dir, "agreement.txt")
        with open(self.sample_doc, "w", encoding="utf-8") as f:
            f.write("Version 1: Original draft content\n")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_create_snapshot_and_list_revisions(self):
        store = DocumentHistoryStore(self.case_dir)
        snap1 = store.create_snapshot("agreement.txt", author="User", comment="Initial snapshot")
        self.assertIsNotNone(snap1)
        self.assertIn("revision_id", snap1)

        # Modify document
        with open(self.sample_doc, "w", encoding="utf-8") as f:
            f.write("Version 2: Edited content by Alix\n")

        snap2 = store.create_snapshot("agreement.txt", author="Alix", comment="Edited section 1")
        self.assertIsNotNone(snap2)

        revisions = store.list_revisions("agreement.txt")
        self.assertEqual(len(revisions), 2)
        self.assertEqual(revisions[0]["author"], "Alix")
        self.assertEqual(revisions[1]["author"], "User")

    def test_rollback_revision(self):
        store = DocumentHistoryStore(self.case_dir)
        snap1 = store.create_snapshot("agreement.txt", author="User", comment="Original version")
        rev1_id = snap1["revision_id"]

        # Apply edit
        with open(self.sample_doc, "w", encoding="utf-8") as f:
            f.write("Version 2: Unwanted changes\n")
        store.create_snapshot("agreement.txt", author="Agent", comment="Unwanted edit")

        # Verify edited content
        with open(self.sample_doc, "r", encoding="utf-8") as f:
            self.assertIn("Unwanted changes", f.read())

        # Perform rollback to rev1
        res = store.rollback_revision("agreement.txt", rev1_id, author="User")
        self.assertIsNotNone(res)

        # Confirm content was restored in-place
        with open(self.sample_doc, "r", encoding="utf-8") as f:
            content = f.read()
            self.assertEqual(content, "Version 1: Original draft content\n")


if __name__ == "__main__":
    unittest.main()

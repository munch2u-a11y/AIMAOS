"""Tests for AIMAOS Document Display & Line-Level Agent Annotations."""
from __future__ import annotations

import os
import tempfile
import unittest

from core.document_review import DocumentReviewStore, format_agent_review_prompt
from core.db.office_sqlite import OfficeSQLite


class TestDocumentDisplayNotes(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.case_dir = os.path.join(self.temp_dir.name, "Casale")
        os.makedirs(self.case_dir, exist_ok=True)
        self.db_path = os.path.join(self.temp_dir.name, "office_database.sqlite")
        
        # Create a sample text file
        self.sample_doc = os.path.join(self.case_dir, "contract_draft.txt")
        with open(self.sample_doc, "w", encoding="utf-8") as f:
            f.write("Line 1: Master Services Agreement\nLine 2: Section 1. Scope of Work\nLine 3: Client shall provide tax identifier.\n")

        # Register case in database
        db = OfficeSQLite(self.db_path)
        db.upsert_case("casale", "Casale", self.case_dir, matter_type="Contract Review", category="legal")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_add_line_anchored_review_note(self):
        store = DocumentReviewStore(self.case_dir)
        note = store.add_note(
            rel_path="contract_draft.txt",
            line_number=3,
            line_text="Line 3: Client shall provide tax identifier.",
            comment="Please request W-9 or TIN from client before finalizing section 1.",
            kind="correction",
        )

        self.assertIsNotNone(note.get("id"))
        self.assertEqual(note.get("line_number"), 3)
        self.assertEqual(note.get("kind"), "correction")
        self.assertEqual(note.get("status"), "open")

        notes = store.list_notes("contract_draft.txt", include_resolved=False)
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0]["line_number"], 3)

    def test_format_agent_review_prompt(self):
        store = DocumentReviewStore(self.case_dir)
        store.add_note(
            rel_path="contract_draft.txt",
            line_number=2,
            line_text="Section 1. Scope of Work",
            comment="Clarify timeline details.",
            kind="question",
        )

        prompt_summary = format_agent_review_prompt(self.case_dir, "contract_draft.txt", line_number=2)
        self.assertIn("Line 2", prompt_summary)
        self.assertIn("Section 1. Scope of Work", prompt_summary)
        self.assertIn("Clarify timeline details", prompt_summary)

    def test_set_note_status_resolve_and_reopen(self):
        store = DocumentReviewStore(self.case_dir)
        note = store.add_note(
            rel_path="contract_draft.txt",
            line_number=1,
            line_text="Master Services Agreement",
            comment="Check title capitalization",
            kind="general",
        )
        note_id = note["id"]

        # Resolve note
        resolved = store.set_note_status(rel_path="contract_draft.txt", note_id=note_id, status="resolved")
        self.assertEqual(resolved["status"], "resolved")

        open_notes = store.list_notes("contract_draft.txt", include_resolved=False)
        self.assertEqual(len(open_notes), 0)

        # Reopen note
        reopened = store.set_note_status(rel_path="contract_draft.txt", note_id=note_id, status="open")
        self.assertEqual(reopened["status"], "open")
        open_notes = store.list_notes("contract_draft.txt", include_resolved=False)
        self.assertEqual(len(open_notes), 1)


if __name__ == "__main__":
    unittest.main()

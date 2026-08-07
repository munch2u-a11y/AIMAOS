"""Tests for AIMAOS Digital Office Workstation UI and Persistent Agent Dock."""
from __future__ import annotations

import unittest
from core.comms.office_board import OfficeBoard


class TestDigitalOfficeUI(unittest.TestCase):
    def setUp(self):
        self.board = OfficeBoard()

    def test_post_quick_task_from_agent_dock(self):
        task_id = self.board.post_task(
            "Review Casale billing statement and draft reminder",
            "User",
            "Finn",
            "HIGH",
            details={"source": "persistent_agent_dock"},
        )
        self.assertIsNotNone(task_id)

        active = self.board.board.get("active_tasks", [])
        posted = next((t for t in active if t.get("id") == task_id), None)
        self.assertIsNotNone(posted)
        self.assertEqual(posted["assigned_agent"], "Finn")
        self.assertEqual(posted["priority"], "HIGH")
        self.assertEqual(posted["details"].get("source"), "persistent_agent_dock")

    def test_assign_quick_task_to_alix_or_kai(self):
        task_id_alix = self.board.post_task("Draft settlement memo", "User", "Alix", "NORMAL")
        task_id_kai = self.board.post_task("Archive closed matter records", "User", "Kai", "ROUTINE")

        active = self.board.board.get("active_tasks", [])
        self.assertTrue(any(t["id"] == task_id_alix and t["assigned_agent"] == "Alix" for t in active))
        self.assertTrue(any(t["id"] == task_id_kai and t["assigned_agent"] == "Kai" for t in active))


if __name__ == "__main__":
    unittest.main()

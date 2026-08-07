"""Tests for Autonomous Self-Repair Workflows and Audit Explanations in AIMAOS."""
from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime

from core.comms.office_board import OfficeBoard
from core.db.office_sqlite import OfficeSQLite
from core.local_calendar import LocalCalendar
from core.workflow_review import build_workstation_items, run_daily_advancement_review


class TestSelfRepair(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp_dir.name, "test_office.sqlite")
        self.board_path = os.path.join(self.tmp_dir.name, "office_board.json")
        self.state_path = os.path.join(self.tmp_dir.name, "workflow_review.json")
        self.calendar_path = os.path.join(self.tmp_dir.name, "local_calendar.json")
        self.calendar = LocalCalendar(path=self.calendar_path)
        self.db = OfficeSQLite(db_path=self.db_path)
        self.board = OfficeBoard(board_file=self.board_path)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_daily_review_triggers_autonomous_self_repair(self):
        # 1. Post a task that completes with an unconfirmed/failed result marker
        task_id = self.board.post_task("Generate Casale settlement agreement", "User", "Alix", "HIGH")
        
        # Simulate task completion with failure marker (no artifact created on disk)
        def mark_unconfirmed(payload):
            active = payload.get("active_tasks", [])
            task = next((t for t in active if t.get("id") == task_id), None)
            if task:
                active.remove(task)
                task["status"] = "completed"
                task["completed_at"] = datetime.now().isoformat()
                task["result"] = "Completed in text, but unconfirmed/failed work: no physical docx file produced on disk."
                payload.setdefault("completed_tasks", []).append(task)

        self.board._locked_mutation(mark_unconfirmed)

        # 2. Run Marley's daily advancement review
        report = run_daily_advancement_review(
            force=True,
            board=self.board,
            calendar=self.calendar,
            state_path=self.state_path,
        )

        self.assertTrue(report.get("ran"))
        self.assertGreaterEqual(report.get("completion_reviews", 0), 1)
        self.assertGreaterEqual(report.get("self_repairs_triggered", 0), 1)

        # 3. Verify active tasks now include the self-repair remediation task for Alix
        active_tasks = self.board.board.get("active_tasks", [])
        repair_task = next((t for t in active_tasks if t.get("details", {}).get("work_type") == "self_repair"), None)
        self.assertIsNotNone(repair_task)
        self.assertEqual(repair_task["assigned_agent"], "Alix")
        self.assertTrue(repair_task["details"].get("auto_requeued"))

        # 4. Verify workstation items include plain-language audit explanations
        items = build_workstation_items(board=self.board, calendar=self.calendar, database=self.db)
        review_item = next((i for i in items if i.get("kind") == "completion_review"), None)
        self.assertIsNotNone(review_item)
        self.assertIn("no verified document file was produced on disk", review_item.get("audit_reason") or "")
        self.assertIn("Self-repair active", review_item.get("self_repair_status") or "")


if __name__ == "__main__":
    unittest.main()

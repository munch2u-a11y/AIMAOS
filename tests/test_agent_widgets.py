"""Tests for AIMAOS agent UI widgets (interactive forms and alert banners)."""
from __future__ import annotations

import json
import os
import tempfile
import unittest

from core.agent_widgets import (
    build_alert_banner,
    build_form_field,
    build_interactive_form,
    validate_widget_schema,
)
from core.comms.office_board import OfficeBoard
from core.workflow_review import (
    build_workstation_items,
    submit_human_form_response,
)


class TestAgentWidgets(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.board_file = os.path.join(self.temp_dir.name, "comms", "office_board.json")
        os.makedirs(os.path.dirname(self.board_file), exist_ok=True)
        os.environ["AIMAOS_ROOT"] = self.temp_dir.name

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_validate_form_schema(self):
        fields = [
            build_form_field("client_name", "Client Name", "text", required=True),
            build_form_field("entity_type", "Entity Type", "select", options=["LLC", "Corporation", "Sole Prop"]),
            build_form_field("notes", "Special Instructions", "textarea", placeholder="Enter notes..."),
        ]
        form = build_interactive_form("Client Information Survey", fields, instructions="Please fill out details.")
        
        raw_payload = {"interactive_form": form}
        validated = validate_widget_schema(raw_payload)

        self.assertIn("interactive_form", validated)
        clean_form = validated["interactive_form"]
        self.assertEqual(clean_form["title"], "Client Information Survey")
        self.assertEqual(len(clean_form["fields"]), 3)
        self.assertEqual(clean_form["fields"][0]["id"], "client_name")
        self.assertTrue(clean_form["fields"][0]["required"])
        self.assertEqual(clean_form["fields"][1]["type"], "select")
        self.assertEqual(len(clean_form["fields"][1]["options"]), 3)

    def test_validate_alert_banner_schema(self):
        banner = build_alert_banner("Urgent Action Required", "Client contract missing signature.", level="urgent", action_label="Review Contract")
        raw_payload = {"alert_banner": banner}
        validated = validate_widget_schema(raw_payload)

        self.assertIn("alert_banner", validated)
        clean_banner = validated["alert_banner"]
        self.assertEqual(clean_banner["level"], "urgent")
        self.assertEqual(clean_banner["title"], "Urgent Action Required")
        self.assertEqual(clean_banner["action_label"], "Review Contract")

    def test_submit_human_form_response(self):
        board = OfficeBoard()
        form_spec = build_interactive_form("Missing Information", [
            build_form_field("tax_id", "Tax ID", "text", required=True)
        ])
        
        task_id = board.post_task(
            "Gather client tax identifier",
            "Alix",
            "Attorney",
            "HIGH",
            details={
                "work_type": "human_follow_up",
                "requires_human": True,
                "interactive_form": form_spec,
                "blocker": "Missing Tax ID for document generation."
            }
        )

        # Update task status to waiting_on_human
        board.update_task_status(task_id, "waiting_on_human")

        # Submit user responses
        user_input = {"tax_id": "12-3456789"}
        updated_task = submit_human_form_response(task_id, user_input, board=board)

        self.assertEqual(updated_task.get("status"), "queued")
        details = updated_task.get("details", {})
        self.assertFalse(details.get("requires_human"))
        self.assertEqual(details.get("user_responses"), user_input)
        self.assertNotIn("blocker", details)

    def test_build_workstation_items_includes_widgets(self):
        board = OfficeBoard()
        form_spec = build_interactive_form("Matter Questionnaire", [
            build_form_field("dob", "Date of Birth", "date")
        ])
        banner_spec = build_alert_banner("Missing Intake Document", "Please upload signed retainer.", level="warning")

        board.post_task(
            "Complete Intake",
            "Finn",
            "Staff",
            "HIGH",
            details={
                "work_type": "human_follow_up",
                "requires_human": True,
                "interactive_form": form_spec,
                "alert_banner": banner_spec,
                "client_name": "Casale",
            }
        )

        items = build_workstation_items(board=board)
        self.assertTrue(len(items) > 0)

        item = next((i for i in items if i["title"] == "Complete Intake"), None)
        self.assertIsNotNone(item)
        self.assertIn("interactive_form", item)
        self.assertIsNotNone(item["interactive_form"])
        self.assertEqual(item["interactive_form"]["title"], "Matter Questionnaire")
        self.assertIn("alert_banner", item)
        self.assertIsNotNone(item["alert_banner"])
        self.assertEqual(item["alert_banner"]["level"], "warning")


if __name__ == "__main__":
    unittest.main()

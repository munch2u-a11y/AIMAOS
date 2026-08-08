import json
from pathlib import Path

import aimaos_ui
import pytest

from core.document_review import DocumentReviewStore


class FakeQueueBoard:
    def __init__(self):
        self.board = {"active_tasks": []}
        self.posted = []

    def post_task(self, title, requester, target_agent, priority, details=None):
        task_id = "task_feedback"
        task = {
            "id": task_id, "title": title, "requester": requester,
            "assigned_agent": target_agent, "priority": priority,
            "status": "queued", "details": details or {},
        }
        self.board["active_tasks"].append(task)
        self.posted.append(task)
        return task_id


def test_document_review_notes_are_durable_agent_readable_and_resolvable(tmp_path):
    case_dir = tmp_path / "matter"
    case_dir.mkdir()
    store = DocumentReviewStore(str(case_dir))

    note = store.add_note(
        rel_path="drafts/motion.docx",
        line_number=12,
        line_text="The hearing is August 8.",
        comment="Verify this date against the signed notice.\nDo not file until confirmed.",
        kind="correction",
    )

    state = json.loads((case_dir / ".aimaos_review_notes.json").read_text(encoding="utf-8"))
    summary = (case_dir / "AIMAOS_REVIEW_NOTES.md").read_text(encoding="utf-8")
    assert state["documents"]["drafts/motion.docx"]["notes"][0]["id"] == note["id"]
    assert "line 12" in summary
    assert "Verify this date" in summary
    assert "do not overwrite source evidence" in summary

    resolved = store.set_note_status(
        rel_path="drafts/motion.docx", note_id=note["id"], status="resolved"
    )
    assert resolved["status"] == "resolved"
    assert store.list_notes("drafts/motion.docx", include_resolved=False) == []
    assert "- [x]" in (case_dir / "AIMAOS_REVIEW_NOTES.md").read_text(encoding="utf-8")


def test_document_review_store_rejects_invalid_note_inputs(tmp_path):
    store = DocumentReviewStore(str(tmp_path))
    with pytest.raises(ValueError):
        store.add_note(
            rel_path="../../outside.docx", line_number=1, line_text="x",
            comment="Change this", kind="correction",
        )
    with pytest.raises(ValueError):
        store.add_note(
            rel_path="draft.docx", line_number=0, line_text="x",
            comment="Change this", kind="correction",
        )
    with pytest.raises(ValueError):
        store.add_note(
            rel_path="draft.docx", line_number=1, line_text="x",
            comment="", kind="correction",
        )


def test_document_review_payload_returns_lines_notes_and_change_warning(tmp_path):
    case_dir = tmp_path / "matter"
    case_dir.mkdir()
    document = case_dir / "draft.txt"
    document.write_text("First line\nSecond line\n", encoding="utf-8")
    store = DocumentReviewStore(str(case_dir))
    store.add_note(
        rel_path="draft.txt", line_number=2, line_text="Second line",
        comment="Replace this sentence.", kind="correction",
    )

    payload = aimaos_ui._document_review_payload(str(case_dir), "draft.txt")
    assert payload["extraction"]["status"] == "extracted"
    assert payload["lines"] == [
        {"number": 1, "text": "First line"},
        {"number": 2, "text": "Second line"},
    ]
    assert payload["notes"][0]["stale"] is False
    assert payload["open_note_count"] == 1
    assert str(case_dir) not in repr(payload)

    document.write_text("First line\nChanged line\n", encoding="utf-8")
    changed = aimaos_ui._document_review_payload(str(case_dir), "draft.txt")
    assert changed["notes"][0]["stale"] is True


def test_document_review_rejects_private_or_outside_case_paths(tmp_path):
    case_dir = tmp_path / "matter"
    private = case_dir / ".private" / "secret.txt"
    private.parent.mkdir(parents=True)
    private.write_text("secret", encoding="utf-8")
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")

    with pytest.raises(aimaos_ui.SecurityValidationError):
        aimaos_ui._document_review_payload(str(case_dir), ".private/secret.txt")
    with pytest.raises(aimaos_ui.SecurityValidationError):
        aimaos_ui._document_review_payload(str(case_dir), "../outside.txt")


def test_open_document_notes_queue_one_safe_agent_task(tmp_path):
    case_dir = tmp_path / "matter"
    case_dir.mkdir()
    (case_dir / "draft.docx").write_bytes(b"synthetic")
    store = DocumentReviewStore(str(case_dir))
    store.add_note(
        rel_path="draft.docx", line_number=1, line_text="Draft heading",
        comment="Use the signed order's date.", kind="correction",
    )
    board = FakeQueueBoard()
    arguments = {
        "case": {"client_name": "Example Client"},
        "slug": "example",
        "case_dir": str(case_dir),
        "normalized_rel": "draft.docx",
        "board": board,
    }

    task_id, created = aimaos_ui._queue_document_feedback(**arguments)
    repeated_id, repeated_created = aimaos_ui._queue_document_feedback(**arguments)

    assert (task_id, created) == ("task_feedback", True)
    assert (repeated_id, repeated_created) == ("task_feedback", False)
    assert len(board.posted) == 1
    details = board.posted[0]["details"]
    assert details["file_path"] == "draft.docx"
    assert details["client_slug"] == "example"
    assert "signed order" not in repr(details)
    assert "apply every open note directly to the document" in details["next_action"]

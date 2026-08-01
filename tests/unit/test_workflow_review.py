import json
from datetime import date, datetime, timedelta

from core.local_calendar import LocalCalendar
from core.workflow_review import (
    build_workstation_items,
    complete_human_task,
    run_daily_advancement_review,
    snooze_human_task,
)


class FakeBoard:
    def __init__(self, *, active=None, completed=None):
        self.board = {
            "active_tasks": list(active or []),
            "completed_tasks": list(completed or []),
            "activity_stream": [],
            "agent_statuses": {},
        }

    def _append_activity(self, payload, message):
        payload["activity_stream"].append({"message": message})

    def _locked_mutation(self, callback):
        return callback(self.board)

    def update_task_status(self, task_id, status, result=None):
        for task in list(self.board["active_tasks"]):
            if task["id"] != task_id:
                continue
            task["status"] = status
            if result:
                task["result"] = result
            if status == "completed":
                task["completed_at"] = datetime.now().isoformat()
                self.board["active_tasks"].remove(task)
                self.board["completed_tasks"].append(task)
            return True
        return False


class FakeDatabase:
    def __init__(self, cases=None):
        self.cases = list(cases or [])

    def list_all_cases(self):
        return self.cases


def _config():
    return {
        "workflow": {
            "daily_review_enabled": True,
            "stale_task_hours": 24,
            "direct_communications": False,
        }
    }


def test_daily_review_turns_client_message_into_idempotent_human_follow_up(tmp_path):
    board = FakeBoard(active=[{
        "id": "task_contact",
        "title": "Send update to SYNTHETIC CLIENT",
        "assigned_agent": "Finn",
        "priority": "NORMAL",
        "status": "queued",
        "created_at": "2026-07-31T08:00:00",
        "details": {"client_name": "SYNTHETIC CLIENT", "draft_message": "private draft"},
    }])
    calendar = LocalCalendar(str(tmp_path / "calendar" / "events.json"))
    state_path = str(tmp_path / "review" / "state.json")

    report = run_daily_advancement_review(
        force=True,
        now=datetime(2026, 7, 31, 9, 0),
        board=board,
        calendar=calendar,
        state_path=state_path,
        config=_config(),
    )

    task = board.board["active_tasks"][0]
    assert report["communications_held"] == 1
    assert task["title"] == "Attorney follow-up: update SYNTHETIC CLIENT"
    assert task["assigned_agent"] == "Attorney"
    assert task["status"] == "waiting_on_human"
    assert task["priority"] == "HIGH"
    assert task["details"]["due_date"] == "2026-07-31"
    assert task["details"]["requires_human"] is True
    assert len(calendar.list_events()) == 1

    again = run_daily_advancement_review(
        force=True,
        now=datetime(2026, 7, 31, 10, 0),
        board=board,
        calendar=calendar,
        state_path=state_path,
        config=_config(),
    )
    assert again["communications_held"] == 0
    assert len(calendar.list_events()) == 1


def test_daily_review_resolves_recursive_dependencies_and_flags_false_completion(tmp_path):
    completed = [{
        "id": "task_a", "title": "Collect records", "status": "completed",
        "completed_at": "2026-07-31T08:00:00", "details": {},
    }, {
        "id": "task_false", "title": "Further case research", "status": "completed",
        "completed_at": "2026-07-31T08:30:00",
        "result": "The work was unconfirmed/failed and no artifact was produced.",
        "details": {"client_name": "SYNTHETIC CLIENT"},
    }]
    active = [{
        "id": "task_b", "title": "Analyze records", "assigned_agent": "Quinn",
        "priority": "NORMAL", "status": "queued", "created_at": "2026-07-31T08:00:00",
        "details": {"blocked_by": ["task_a"]},
    }, {
        "id": "task_c", "title": "Draft response", "assigned_agent": "Alix",
        "priority": "NORMAL", "status": "queued", "created_at": "2026-07-31T08:00:00",
        "details": {"blocked_by": ["task_b"]},
    }]
    board = FakeBoard(active=active, completed=completed)
    calendar = LocalCalendar(str(tmp_path / "calendar.json"))
    kwargs = {
        "force": True,
        "now": datetime(2026, 7, 31, 9, 0),
        "board": board,
        "calendar": calendar,
        "state_path": str(tmp_path / "state.json"),
        "config": _config(),
    }

    report = run_daily_advancement_review(**kwargs)
    by_id = {task["id"]: task for task in board.board["active_tasks"]}
    assert by_id["task_b"]["status"] == "queued"
    assert by_id["task_c"]["status"] == "blocked"
    assert report["dependency_blocked"] == 1
    reviews = [task for task in by_id.values() if task["details"].get("work_type") == "completion_review"]
    assert len(reviews) == 1
    assert reviews[0]["status"] == "waiting_on_human"

    board.update_task_status("task_b", "completed", result="Artifact verified.")
    report = run_daily_advancement_review(**kwargs)
    by_id = {task["id"]: task for task in board.board["active_tasks"]}
    assert by_id["task_c"]["status"] == "queued"
    assert report["dependency_released"] == 1
    assert len([task for task in by_id.values() if task["details"].get("work_type") == "completion_review"]) == 1


def test_workstation_merges_case_work_and_supports_human_actions(tmp_path):
    case_dir = tmp_path / "matter"
    case_dir.mkdir()
    (case_dir / ".client_file_state.json").write_text(json.dumps({
        "client_name": "Example Client",
        "next_steps": ["Prepare for the hearing."],
        "required_documents": {"Signed affidavit": {"status": "Pending"}},
    }), encoding="utf-8")
    task = {
        "id": "task_human", "title": "Attorney follow-up: update Example Client",
        "assigned_agent": "Attorney", "priority": "HIGH", "status": "waiting_on_human",
        "details": {
            "client_name": "Example Client", "requires_human": True,
            "due_date": date.today().isoformat(), "work_type": "human_follow_up",
            "blocker": "Attorney review required.", "next_action": "Call the client.",
        },
    }
    board = FakeBoard(active=[task])
    calendar = LocalCalendar(str(tmp_path / "calendar.json"))
    calendar.upsert_event(
        event_key="communication:task_human", title=task["title"],
        date=date.today().isoformat(), source_task_id="task_human", kind="human_follow_up",
    )
    items = build_workstation_items(
        board=board,
        calendar=calendar,
        database=FakeDatabase([{
            "client_slug": "example", "client_name": "Example Client",
            "path": str(case_dir), "status": "open", "category": "active",
        }]),
    )

    assert len([item for item in items if item["id"] == "task_human"]) == 1
    assert any(item["kind"] == "case_advancement" and item["status"] == "blocked" for item in items)

    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    snooze_human_task("task_human", tomorrow, board=board, calendar=calendar)
    assert board.board["active_tasks"][0]["details"]["due_date"] == tomorrow
    assert calendar.list_events()[0]["date"] == tomorrow

    complete_human_task("task_human", board=board, calendar=calendar)
    assert not board.board["active_tasks"]
    assert calendar.list_events() == []


def test_workstation_resolves_safe_task_file_targets_without_exposing_absolute_paths(tmp_path):
    case_dir = tmp_path / "matter"
    drafts = case_dir / "drafts"
    drafts.mkdir(parents=True)
    document = drafts / "response.docx"
    document.write_bytes(b"synthetic")
    (case_dir / ".client_file_state.json").write_text(json.dumps({
        "client_name": "Example Client", "next_steps": [], "required_documents": {},
    }), encoding="utf-8")
    source = {
        "id": "task_source", "title": "Create response", "status": "completed",
        "details": {"client_name": "Example Client", "output_path": str(document)},
    }
    review = {
        "id": "task_review", "title": "Review response", "assigned_agent": "Attorney",
        "priority": "HIGH", "status": "waiting_on_human",
        "details": {
            "client_name": "Example Client", "source_task_id": "task_source",
            "requires_human": True, "work_type": "completion_review",
        },
    }
    items = build_workstation_items(
        board=FakeBoard(active=[review], completed=[source]),
        calendar=LocalCalendar(str(tmp_path / "calendar.json")),
        database=FakeDatabase([{
            "client_slug": "example", "client_name": "Example Client",
            "path": str(case_dir), "status": "open", "category": "active",
        }]),
    )

    item = next(value for value in items if value["id"] == "task_review")
    assert item["review_target"] == {
        "client_slug": "example", "file_path": "drafts/response.docx", "file_name": "response.docx",
    }
    assert str(case_dir) not in repr(item)


def test_daily_review_runs_only_once_per_day_without_force(tmp_path):
    kwargs = {
        "now": datetime(2026, 7, 31, 9, 0),
        "board": FakeBoard(),
        "calendar": LocalCalendar(str(tmp_path / "calendar.json")),
        "state_path": str(tmp_path / "state.json"),
        "config": _config(),
    }
    assert run_daily_advancement_review(**kwargs)["ran"] is True
    second = run_daily_advancement_review(**kwargs)
    assert second["ran"] is False
    assert second["reason"] == "already_reviewed"

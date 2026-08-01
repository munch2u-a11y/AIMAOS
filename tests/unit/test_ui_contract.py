import ast
import re
from pathlib import Path

import aimaos_ui


ROOT = Path(__file__).resolve().parents[2]


def test_public_case_contract_never_exposes_storage_path():
    public = aimaos_ui._public_case({
        "client_slug": "sample",
        "client_name": "Sample",
        "path": "/private/client/files",
        "status": "open",
    })
    assert public == {"client_slug": "sample", "client_name": "Sample", "status": "open"}
    assert "/private" not in repr(public)


def test_public_progress_contract_drops_arguments_paths_and_internal_errors():
    task = aimaos_ui._public_task({
        "id": "task_1", "title": "Review", "status": "queued",
        "details": {"path": "/private/client"}, "result": "raw",
    })
    assert task == {"id": "task_1", "title": "Review", "status": "queued"}
    job = aimaos_ui._public_job({
        "job_id": "job_1", "kind": "test", "title": "Test", "status": "failed",
        "error": "Traceback at /private/client",
    })
    assert "/private" not in repr(job)
    assert "Traceback" not in repr(job)


def test_browser_safe_values_redact_application_root():
    value = aimaos_ui._browser_safe_value({"message": f"Saved at {aimaos_ui.AIMAOS_ROOT}/private.docx"})
    assert aimaos_ui.AIMAOS_ROOT not in repr(value)


def test_daemon_pause_control_round_trip(monkeypatch, tmp_path):
    control_path = tmp_path / "comms" / "daemon_control.json"
    monkeypatch.setattr(aimaos_ui, "DAEMON_CONTROL_PATH", str(control_path))

    assert aimaos_ui._read_daemon_control() == {"pause_requested": False}
    paused = aimaos_ui._set_daemon_pause_request(True)
    assert paused["pause_requested"] is True
    assert aimaos_ui._read_daemon_control()["pause_requested"] is True

    resumed = aimaos_ui._set_daemon_pause_request(False)
    assert resumed["pause_requested"] is False
    assert aimaos_ui._read_daemon_control()["pause_requested"] is False


def test_dashboard_case_paths_reject_private_runtime_files(tmp_path):
    private = tmp_path / ".case_agent" / "mrag_data" / "memory.json"
    private.parent.mkdir(parents=True)
    private.write_text("private", encoding="utf-8")
    try:
        aimaos_ui._resolve_public_case_file(str(tmp_path), ".case_agent/mrag_data/memory.json")
    except aimaos_ui.SecurityValidationError:
        pass
    else:
        raise AssertionError("dashboard exposed a private case-agent runtime file")


def test_ui_avoids_unsafe_rendering_and_remote_assets():
    javascript = (ROOT / "ui" / "static" / "app.js").read_text(encoding="utf-8")
    html = (ROOT / "ui" / "aimaos_ui.html").read_text(encoding="utf-8")
    combined = javascript + html
    assert "innerHTML" not in combined
    assert "outerHTML" not in combined
    assert "document.write" not in combined
    assert "fonts.googleapis.com" not in combined
    assert "https://" not in html


def test_javascript_id_selectors_exist_in_dashboard_markup():
    javascript = (ROOT / "ui" / "static" / "app.js").read_text(encoding="utf-8")
    html = (ROOT / "ui" / "aimaos_ui.html").read_text(encoding="utf-8")
    html_ids = set(re.findall(r'id="([A-Za-z][A-Za-z0-9_-]*)"', html))
    selected_ids = set(re.findall(r'\$\("#([A-Za-z][A-Za-z0-9_-]*)"\)', javascript))
    assert selected_ids <= html_ids
    assert "setup-banner" in selected_ids
    assert {"view-agenda", "agenda-work-list", "attention-metric"} <= html_ids
    assert {
        "document-review-dialog", "document-review-lines", "document-review-note-form",
        "document-review-notes", "document-review-submit",
    } <= html_ids


def test_ui_routes_use_background_jobs_for_model_work():
    source = (ROOT / "aimaos_ui.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    assert any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "submit"
        for node in ast.walk(tree)
    )
    assert ".process_client_file(" not in source
    assert "setup_required" in source


def test_template_catalog_flags_incomplete_provenance():
    catalog = aimaos_ui._template_catalog()
    assert catalog
    assert all(item["verification_status"] in {"verified", "review_required"} for item in catalog)

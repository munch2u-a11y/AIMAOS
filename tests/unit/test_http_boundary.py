import json
import threading
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer

import aimaos_ui
import pytest


def _request(url, *, token=None, method="GET", csrf=None, body=None):
    headers = {}
    if token:
        headers["X-AIMAOS-Token"] = token
    if csrf:
        headers["X-AIMAOS-CSRF"] = csrf
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")
    return urllib.request.urlopen(urllib.request.Request(
        url, data=data, headers=headers, method=method
    ), timeout=3)


def test_http_auth_csrf_and_security_headers(monkeypatch):
    monkeypatch.setenv("AIMAOS_UI_TOKEN", "test-token")
    try:
        server = ThreadingHTTPServer(("127.0.0.1", 0), aimaos_ui.AIMAOSUIHandler)
    except PermissionError:
        pytest.skip("execution sandbox does not permit loopback sockets")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with urllib.request.urlopen(f"{base}/", timeout=3) as response:
            assert response.status == 200
            assert "default-src 'self'" in response.headers["Content-Security-Policy"]
            assert response.headers["X-Frame-Options"] == "DENY"

        try:
            _request(f"{base}/api/bootstrap")
        except urllib.error.HTTPError as exc:
            assert exc.code == 401
        else:
            raise AssertionError("API accepted a request without its configured token")

        with _request(f"{base}/api/bootstrap", token="test-token") as response:
            payload = json.load(response)
            assert response.status == 200
            assert payload["csrf_token"] == aimaos_ui.CSRF_TOKEN

        try:
            _request(
                f"{base}/api/quick_action",
                token="test-token",
                method="POST",
                body={"action": "audit_all"},
            )
        except urllib.error.HTTPError as exc:
            assert exc.code == 403
        else:
            raise AssertionError("Mutation succeeded without a CSRF token")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_document_review_http_flow(monkeypatch, tmp_path):
    monkeypatch.delenv("AIMAOS_UI_TOKEN", raising=False)
    case_dir = tmp_path / "matter"
    case_dir.mkdir()
    (case_dir / "draft.txt").write_text("Heading\nDate is August 8\n", encoding="utf-8")
    case = {"client_slug": "example", "client_name": "Example Client", "path": str(case_dir)}
    monkeypatch.setattr(
        aimaos_ui.AIMAOSUIHandler, "_case_record", lambda _self, _slug: (case, str(case_dir))
    )
    monkeypatch.setattr(aimaos_ui, "_setup_complete", lambda: True)
    class FakeAuditBoard:
        def log_activity(self, _message):
            return None

    monkeypatch.setattr(aimaos_ui, "OfficeBoard", FakeAuditBoard)
    monkeypatch.setattr(
        aimaos_ui, "_queue_document_feedback",
        lambda **_kwargs: ("task_document_feedback", True),
    )
    monkeypatch.setattr(
        aimaos_ui, "_queue_case_specialist_refresh",
        lambda **_kwargs: "job_case_review",
    )
    try:
        server = ThreadingHTTPServer(("127.0.0.1", 0), aimaos_ui.AIMAOSUIHandler)
    except PermissionError:
        pytest.skip("execution sandbox does not permit loopback sockets")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    review_url = f"{base}/api/document_review?slug=example&path={urllib.parse.quote('draft.txt')}"
    try:
        with _request(f"{base}/api/bootstrap") as response:
            csrf = json.load(response)["csrf_token"]
        with _request(review_url) as response:
            review = json.load(response)
        assert review["lines"][1] == {"number": 2, "text": "Date is August 8"}

        with _request(
            f"{base}/api/document_review_note", method="POST", csrf=csrf,
            body={
                "slug": "example", "path": "draft.txt", "action": "create",
                "line_number": 2, "kind": "correction",
                "comment": "Confirm against the signed notice.",
            },
        ) as response:
            saved = json.load(response)
        assert saved["status"] == "success"
        assert (case_dir / "AIMAOS_REVIEW_NOTES.md").is_file()

        with _request(review_url) as response:
            refreshed = json.load(response)
        assert refreshed["open_note_count"] == 1
        assert refreshed["notes"][0]["line_number"] == 2

        with _request(
            f"{base}/api/document_review_submit", method="POST", csrf=csrf,
            body={"slug": "example", "path": "draft.txt"},
        ) as response:
            queued = json.load(response)
        assert queued["task_id"] == "task_document_feedback"
        assert queued["review_job_id"] == "job_case_review"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_daemon_pause_resume_http_flow(monkeypatch):
    monkeypatch.delenv("AIMAOS_UI_TOKEN", raising=False)
    monkeypatch.setattr(aimaos_ui, "_setup_complete", lambda: True)
    daemon = {"responsive": True, "state": "ready", "pause_requested": False}
    starts = []

    def daemon_status():
        return dict(daemon)

    def set_pause_request(paused, *, requested_by="user"):
        daemon["pause_requested"] = paused
        daemon["state"] = "paused" if paused else "ready"
        return {"pause_requested": paused, "requested_by": requested_by}

    monkeypatch.setattr(aimaos_ui, "_daemon_status", daemon_status)
    monkeypatch.setattr(aimaos_ui, "_set_daemon_pause_request", set_pause_request)
    monkeypatch.setattr(aimaos_ui, "_start_daemon_process", lambda: starts.append(True))
    try:
        server = ThreadingHTTPServer(("127.0.0.1", 0), aimaos_ui.AIMAOSUIHandler)
    except PermissionError:
        pytest.skip("execution sandbox does not permit loopback sockets")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with _request(f"{base}/api/bootstrap") as response:
            csrf = json.load(response)["csrf_token"]

        with _request(
            f"{base}/api/daemon/pause", method="POST", csrf=csrf, body={},
        ) as response:
            paused = json.load(response)
        assert paused["pause_requested"] is True
        assert paused["daemon"]["state"] == "paused"
        assert starts == []

        daemon["responsive"] = False
        with _request(
            f"{base}/api/daemon/resume", method="POST", csrf=csrf, body={},
        ) as response:
            resumed = json.load(response)
        assert resumed["pause_requested"] is False
        assert starts == [True]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)

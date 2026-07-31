import json
import threading
import urllib.error
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

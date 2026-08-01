import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CONNECTOR_PATH = (
    ROOT / "starter_packs/document_heavy/Alix-AI/business/watchers/email_connector.py"
)
GATEWAY_PATH = ROOT / "starter_packs/document_heavy/Finn-AI/tools/commandeer_channel.py"


def _load_connector():
    spec = importlib.util.spec_from_file_location("aimaos_test_email_connector", CONNECTOR_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_read_only_email_is_blocked_and_logged_truthfully(monkeypatch, tmp_path):
    module = _load_connector()
    log_path = tmp_path / "outbound_email_log.json"
    monkeypatch.setattr(module, "OUTBOUND_LOG_FILE", str(log_path))
    monkeypatch.delenv("AIMAOS_EMAIL_SECURITY_MODE", raising=False)
    monkeypatch.delenv("AIMAOS_SMTP_SEND", raising=False)

    connector = module.EmailConnector({
        "security_mode": "READ_ONLY",
        "approved_recipients": [],
        "username": "office@example.invalid",
        "password": "",
    })
    result = connector.send_email(
        "recipient@example.invalid", "Synthetic subject", "Synthetic body"
    )

    assert "SECURITY POLICY BLOCKED" in result
    record = json.loads(log_path.read_text(encoding="utf-8"))[-1]
    assert record["status"] == "BLOCKED_BY_POLICY"
    assert record["recipient"] == "recipient@example.invalid"


def test_gateway_copy_does_not_claim_every_request_was_dispatched():
    source = GATEWAY_PATH.read_text(encoding="utf-8")
    assert 'delivered = ": DISPATCHED (" in res.upper()' in source
    assert 'outcome = "dispatched" if delivered else "not dispatched"' in source
    assert "Outbound communication dispatched to" not in source

import json
import os

import pytest

from core.atomic_io import atomic_write_json
from core.comms import bus as bus_module
from core.security import SecurityValidationError


def test_atomic_private_writes_replace_complete_content(tmp_path):
    path = tmp_path / "record.json"
    atomic_write_json(str(path), {"version": 1})
    atomic_write_json(str(path), {"version": 2, "complete": True})
    assert json.loads(path.read_text(encoding="utf-8")) == {"version": 2, "complete": True}
    if os.name == "posix":
        assert path.stat().st_mode & 0o777 == 0o600


def test_bus_validates_agent_paths_and_writes_complete_envelopes(tmp_path, monkeypatch):
    monkeypatch.setattr(bus_module, "COMMS_BASE_DIR", str(tmp_path / "comms"))
    bus = bus_module.AgentCompanyBus("Finn")
    with pytest.raises(SecurityValidationError):
        bus.send_message("../../outside", "review", {})
    message_id = bus.send_message("Kai", "review", {"matter": "synthetic"})
    path = tmp_path / "comms" / "Kai" / "inbox" / f"{message_id}.json"
    envelope = json.loads(path.read_text(encoding="utf-8"))
    assert envelope["sender"] == "Finn"
    assert envelope["recipient"] == "Kai"

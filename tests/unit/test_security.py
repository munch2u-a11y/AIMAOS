from pathlib import Path

import pytest

from core.security import (
    SecurityValidationError,
    normalize_slug,
    resolve_within,
    sanitize_filename,
    tool_execution_policy,
    validate_agent_name,
)


def test_resolve_within_blocks_traversal_and_prefix_tricks(tmp_path):
    root = tmp_path / "work"
    root.mkdir()
    assert resolve_within(str(root), "matter", "file.txt").startswith(str(root))
    with pytest.raises(SecurityValidationError):
        resolve_within(str(root), "..", "secret.txt")
    with pytest.raises(SecurityValidationError):
        resolve_within(str(root), str(tmp_path / "work-elsewhere"))


def test_resolve_within_blocks_symlink_escape(tmp_path):
    root = tmp_path / "work"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (root / "escape").symlink_to(outside, target_is_directory=True)
    with pytest.raises(SecurityValidationError):
        resolve_within(str(root), "escape", "record.txt")


@pytest.mark.parametrize("name", ["../record.pdf", r"..\record.pdf", "/tmp/record.pdf"])
def test_upload_filename_drops_path_components(name):
    assert sanitize_filename(name) == "record.pdf"


def test_upload_filename_enforces_extension_allowlist():
    with pytest.raises(SecurityValidationError):
        sanitize_filename("payload.html")
    with pytest.raises(SecurityValidationError):
        sanitize_filename("payload.exe")


def test_slugs_and_agent_names_reject_code_and_paths():
    assert normalize_slug("Smith & Jones") == "smith_jones"
    for value in ("../Smith", "Smith/Other", "Smith;rm"):
        with pytest.raises(SecurityValidationError):
            validate_agent_name(value)


def test_beta_tool_policy_defaults_to_no_external_or_developer_actions():
    cfg = {
        "ui": {"developer_mode": False},
        "security": {
            "allow_network_tools": False,
            "allow_external_mutations": False,
            "allow_shell_tools": False,
        },
    }
    allowed, reason = tool_execution_policy("send_email", {}, cfg)
    assert not allowed and "disabled" in reason
    allowed, reason = tool_execution_policy("clone_agent", {}, cfg)
    assert not allowed and "developer mode" in reason
    allowed, reason = tool_execution_policy("calculator", {}, cfg)
    assert allowed and reason is None


def test_network_and_path_arguments_are_policy_guarded(tmp_path):
    cfg = {
        "ui": {"developer_mode": False},
        "storage": {"allowed_roots": [str(tmp_path)]},
        "security": {"allow_network_tools": False},
    }
    allowed, reason = tool_execution_policy("web_fetch", {"url": "https://example.com"}, cfg)
    assert not allowed and "Network tool" in reason
    allowed, reason = tool_execution_policy("edit_image", {"image_path": "/etc/passwd"}, cfg)
    assert not allowed and "approved storage" in reason


def test_sensitive_runtime_and_credential_paths_are_denied(tmp_path):
    cfg = {"storage": {"allowed_roots": [str(tmp_path)]}}
    for relative in (".git/config", ".env", "comms/office_board.json", ".memory/raw.json"):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("secret", encoding="utf-8")
        allowed, reason = tool_execution_policy("read_file", {"path": str(path)}, cfg)
        assert not allowed and "approved storage" in reason

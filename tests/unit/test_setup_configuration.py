import os

import pytest
import yaml

import setup as setup_app


def _write_config(path):
    path.write_text(
        yaml.safe_dump(
            {
                "llm": {
                    "ollama_host": "http://127.0.0.1:11434",
                    "default_model": "qwen3.5:4b",
                },
                "agents": {
                    "Alix": {"model": "qwen3.5:4b"},
                    "Finn": {"model": "qwen3.5:0.8b"},
                    "Quinn": {"model": "qwen3.5:4b", "research_model": "gemma3:4b"},
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def test_model_choice_updates_default_inheritors_and_preserves_specialists(tmp_path, monkeypatch):
    config_path = tmp_path / "aimaos_config.yaml"
    _write_config(config_path)
    monkeypatch.setattr(setup_app, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(setup_app, "get_installed_ollama_models", lambda host: [])

    setup_app.configure_models_and_pull(
        selected_model="qwen3.5:2b", pull_permission=False, interactive=False
    )

    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert config["llm"]["default_model"] == "qwen3.5:2b"
    assert config["agents"]["Alix"]["model"] == "qwen3.5:2b"
    assert config["agents"]["Quinn"]["model"] == "qwen3.5:2b"
    assert config["agents"]["Quinn"]["research_model"] == "gemma3:4b"
    assert config["agents"]["Finn"]["model"] == "qwen3.5:0.8b"
    if os.name == "posix":
        assert config_path.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("value", ["", "../model", "model\nname", "model:"])
def test_rejects_unsafe_model_tags(value):
    with pytest.raises(ValueError):
        setup_app._validated_model_tag(value)


@pytest.mark.parametrize("value", ["missing-at.example.com", "a@example", "a@example.com\nINJECT=x"])
def test_rejects_invalid_email_configuration(value):
    with pytest.raises(ValueError):
        setup_app._validated_email(value)

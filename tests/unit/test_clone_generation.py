import ast
import importlib.util
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]


def _load_clone_tool():
    path = ROOT / "starter_packs" / "document_heavy" / "Rae-AI" / "tools" / "clone_agent.py"
    spec = importlib.util.spec_from_file_location("test_clone_tool", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_generated_agent_code_is_syntax_safe_for_quoted_role(tmp_path, monkeypatch):
    module = _load_clone_tool()
    config_path = tmp_path / "aimaos_config.yaml"
    config_path.write_text(yaml.safe_dump({"agents": {}}), encoding="utf-8")
    monkeypatch.setattr(module, "AIMAOS_ROOT", str(tmp_path))
    monkeypatch.setattr(module, "CONFIG_PATH", str(config_path))
    monkeypatch.setattr(module, "seed_initial_mrag_beliefs", lambda *_args: None)

    result = module.execute("Nova", 'Review "quoted" records')
    generated = tmp_path / "Nova-AI" / "core" / "agent.py"
    assert result.startswith("Successfully")
    ast.parse(generated.read_text(encoding="utf-8"))


def test_clone_rejects_path_and_code_like_names(tmp_path, monkeypatch):
    module = _load_clone_tool()
    monkeypatch.setattr(module, "AIMAOS_ROOT", str(tmp_path))
    for value in ("../Nova", "Nova-Agent", "Nova;touch"):
        assert module.execute(value, "Reviewer").startswith("Error:")

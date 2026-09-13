import json
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = REPO_ROOT / "plugins" / "aimaos-case-specialist"


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_dual_runtime_manifests_share_the_same_skill():
    codex = load_json(PLUGIN_ROOT / ".codex-plugin" / "plugin.json")
    claude = load_json(PLUGIN_ROOT / ".claude-plugin" / "plugin.json")
    assert codex["name"] == claude["name"] == "aimaos-case-specialist"
    assert codex["version"] == claude["version"]
    assert codex["skills"] == claude["skills"] == "./skills/"
    assert (PLUGIN_ROOT / "skills" / "manage-case-specialist" / "SKILL.md").is_file()


def test_repo_local_marketplace_resolves_plugin_source():
    marketplace = load_json(REPO_ROOT / ".agents" / "plugins" / "marketplace.json")
    assert marketplace["name"] == "aimaos-local"
    entry = next(item for item in marketplace["plugins"] if item["name"] == "aimaos-case-specialist")
    assert entry["source"]["source"] == "local"
    assert (REPO_ROOT / entry["source"]["path"]).resolve() == PLUGIN_ROOT.resolve()


def test_codex_skill_ui_metadata_and_operations_are_complete():
    skill_root = PLUGIN_ROOT / "skills" / "manage-case-specialist"
    metadata = yaml.safe_load((skill_root / "agents" / "openai.yaml").read_text(encoding="utf-8"))
    assert metadata["interface"]["display_name"] == "AIMAOS Case Specialist"
    assert "$manage-case-specialist" in metadata["interface"]["default_prompt"]
    skill = (skill_root / "SKILL.md").read_text(encoding="utf-8")
    for operation in ("initialize", "refresh", "status", "audit", "dry-run"):
        assert f"`{operation}`" in skill
    assert (skill_root / "scripts" / "manage_case_specialist.py").is_file()
    assert (skill_root / "references" / "operations.md").is_file()

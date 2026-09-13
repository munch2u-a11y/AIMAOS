#!/usr/bin/env python3
"""Read-only deployment diagnostics for AIMAOS public beta."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path

from core.platform_support import find_libreoffice, launch_command

ROOT = Path(__file__).resolve().parent
REQUIRED_MODULES = {
    "yaml": "PyYAML",
    "rich": "rich",
    "ollama": "ollama",
    "requests": "requests",
    "docxtpl": "docxtpl",
    "docx": "python-docx",
    "pypdf": "pypdf",
}


@dataclass
class Check:
    name: str
    status: str
    detail: str


def _config() -> dict:
    try:
        import yaml
        return yaml.safe_load((ROOT / "aimaos_config.yaml").read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def _ollama_models(host: str) -> list[str] | None:
    try:
        with urllib.request.urlopen(f"{host.rstrip('/')}/api/tags", timeout=3) as response:
            return [item["name"] for item in json.load(response).get("models", [])]
    except Exception:
        return None


def run_checks() -> list[Check]:
    checks = []
    version_ok = sys.version_info >= (3, 11)
    checks.append(Check("Python", "pass" if version_ok else "fail", sys.version.split()[0]))

    missing = [package for module, package in REQUIRED_MODULES.items()
               if importlib.util.find_spec(module) is None]
    checks.append(Check(
        "Runtime dependencies", "pass" if not missing else "fail",
        "installed" if not missing else f"missing: {', '.join(missing)}",
    ))

    config_path = ROOT / "aimaos_config.yaml"
    cfg = _config()
    checks.append(Check(
        "Configuration", "pass" if config_path.is_file() and cfg else "fail",
        str(config_path),
    ))

    writable = os.access(ROOT, os.W_OK)
    checks.append(Check("Application storage", "pass" if writable else "fail", str(ROOT)))

    agents = sorted(path.name for path in ROOT.glob("*-AI") if path.is_dir())
    checks.append(Check(
        "Starter setup", "pass" if agents else "warn",
        f"{len(agents)} agent workspaces" if agents else f"not materialized; run {launch_command('setup.py')}",
    ))

    llm_cfg = cfg.get("llm", {})
    host = llm_cfg.get("ollama_host", "http://localhost:11434")
    models = _ollama_models(host)
    if models is None:
        checks.append(Check("Local model service", "warn", f"Ollama is not reachable at {host}"))
    else:
        needed = {llm_cfg.get("default_model")}
        needed.update(item.get("model") for item in cfg.get("agents", {}).values())
        missing_models = sorted(model for model in needed if model and model not in models)
        checks.append(Check(
            "Local model service", "pass" if not missing_models else "warn",
            f"reachable; missing configured models: {', '.join(missing_models)}"
            if missing_models else f"reachable; {len(models)} model(s) installed",
        ))

    ui_cfg = cfg.get("ui", {})
    host_setting = str(ui_cfg.get("host", "127.0.0.1"))
    secure_network = host_setting in {"127.0.0.1", "::1", "localhost"} and not ui_cfg.get("allow_lan")
    checks.append(Check(
        "Network default", "pass" if secure_network else "warn",
        "loopback only" if secure_network else "review LAN/TLS/token configuration",
    ))

    security = cfg.get("security", {})
    risky = [name for name in ("allow_network_tools", "allow_external_mutations", "allow_shell_tools", "allow_document_delegation")
             if security.get(name)]
    checks.append(Check(
        "Action policy", "pass" if not risky else "warn",
        "safe beta defaults" if not risky else f"enabled capabilities: {', '.join(risky)}",
    ))

    template_root = ROOT / "starter_packs" / "document_heavy" / "Alix-AI" / "templates"
    templates = list(template_root.glob("*/template.docx"))
    metadata = list(template_root.glob("*/template.yaml"))
    checks.append(Check(
        "Document templates", "pass" if templates and len(templates) == len(metadata) else "warn",
        f"{len(templates)} templates; {len(metadata)} metadata files",
    ))

    libreoffice = find_libreoffice()
    checks.append(Check(
        "Native document conversion", "pass" if libreoffice else "warn",
        f"LibreOffice found at {libreoffice}" if libreoffice else "LibreOffice not found; DOCX remains available",
    ))
    return checks


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Check whether AIMAOS is ready to start")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    parser.add_argument("--strict", action="store_true", help="Treat warnings as failures")
    args = parser.parse_args(argv)
    checks = run_checks()
    if args.json:
        print(json.dumps({"checks": [asdict(check) for check in checks]}, indent=2))
    else:
        print("AIMAOS public-beta deployment check")
        print("=" * 38)
        for check in checks:
            print(f"[{check.status.upper():4}] {check.name}: {check.detail}")
    failures = any(check.status == "fail" for check in checks)
    warnings = any(check.status == "warn" for check in checks)
    return 1 if failures or (args.strict and warnings) else 0


if __name__ == "__main__":
    raise SystemExit(main())

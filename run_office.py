#!/usr/bin/env python3
"""AIMAOS entrypoint: starts Marley's autonomous office daemon.

Usage:
    python run_office.py [--max-cycles N] [--poll SEC]
"""
import os

def _find_aimaos_root():
    p = os.path.dirname(os.path.abspath(__file__))
    while p != os.path.dirname(p) and not os.path.exists(os.path.join(p, "aimaos_config.yaml")):
        p = os.path.dirname(p)
    return p
AIMAOS_ROOT = os.environ.get("AIMAOS_ROOT") or _find_aimaos_root()
if os.name == "posix":
    os.umask(0o077)
import sys
import importlib.util

spec = importlib.util.spec_from_file_location(
    "aimaos_office_daemon", os.path.join(AIMAOS_ROOT, "Marley-AI/core/office_daemon.py"))
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)

if __name__ == "__main__":
    mod.main()

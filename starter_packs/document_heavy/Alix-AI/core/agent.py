"""Every agent's entry point lives at <Name>-AI/core/agent.py (the daemon,
UI, and tests all load it by that convention) — but Alix's own business
logic (document_engine, memory, subagents, watchers) had to move to
Alix-AI/business/ to stop colliding with the shared kernel's top-level
core/ package (both were named "core", so `from core.X import Y` always
resolved to whichever was first on sys.path). This shim keeps the uniform
loading convention intact for every caller without special-casing Alix.
"""
import os

def _find_aimaos_root():
    p = os.path.dirname(os.path.abspath(__file__))
    while p != os.path.dirname(p) and not os.path.exists(os.path.join(p, "aimaos_config.yaml")):
        p = os.path.dirname(p)
    return p
AIMAOS_ROOT = os.environ.get("AIMAOS_ROOT") or _find_aimaos_root()
import sys

sys.path.insert(0, os.path.join(AIMAOS_ROOT, "Alix-AI"))
from business.agent import AlixAgent, Agent

"""Compatibility entry point for the hardened AIMAOS dashboard."""
import sys
from pathlib import Path

ROOT = str(Path(__file__).resolve().parents[1])
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from aimaos_ui import AIMAOSUIHandler, launch_aimaos_ui

AIMAOSHTTPHandler = AIMAOSUIHandler


def start_server(port=8080):
    launch_aimaos_ui(port=port)


if __name__ == "__main__":
    start_server()

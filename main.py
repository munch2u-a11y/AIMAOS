import os

def _find_aimaos_root():
    p = os.path.dirname(os.path.abspath(__file__))
    while p != os.path.dirname(p) and not os.path.exists(os.path.join(p, "aimaos_config.yaml")):
        p = os.path.dirname(p)
    return p
AIMAOS_ROOT = os.environ.get("AIMAOS_ROOT") or _find_aimaos_root()
import sys
import logging

sys.path.insert(0, AIMAOS_ROOT)
from aimaos_ui import launch_aimaos_ui

def main():
    launch_aimaos_ui(port=8080, open_browser=True)

if __name__ == "__main__":
    main()

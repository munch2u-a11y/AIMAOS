import os
import sys
import logging

sys.path.insert(0, "/path/to/AIMAOS")
from aimaos_ui import launch_aimaos_ui

def main():
    launch_aimaos_ui(port=8080, open_browser=True)

if __name__ == "__main__":
    main()

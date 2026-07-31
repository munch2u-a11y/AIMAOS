"""Compatibility entry point for the hardened AIMAOS dashboard."""
from aimaos_ui import AIMAOSUIHandler, launch_aimaos_ui

AIMAOSHTTPHandler = AIMAOSUIHandler


def start_server(port=8080):
    launch_aimaos_ui(port=port)


if __name__ == "__main__":
    start_server()

#!/usr/bin/env python3
"""AIMAOS Standalone Desktop Application Entry Point.

Boots the local AIMAOS server and office daemon, and opens the workstation UI inside
its own self-contained desktop app window titled "AIMAOS".
"""
from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import threading
import time

def _find_aimaos_root() -> str:
    path = os.path.abspath(__file__)
    while path != os.path.dirname(path):
        if os.path.exists(os.path.join(path, "aimaos_config.yaml")):
            return path
        path = os.path.dirname(path)
    return os.path.dirname(os.path.abspath(__file__))

AIMAOS_ROOT = os.environ.get("AIMAOS_ROOT") or _find_aimaos_root()
sys.path.insert(0, AIMAOS_ROOT)

from core.desktop_launcher import launch_desktop_window
from aimaos_ui import launch_aimaos_ui, load_security_config

logger = logging.getLogger("aimaos.app")


def main(argv=None) -> int:
    if os.name == "posix":
        os.umask(0o077)

    cfg = load_security_config().get("ui", {})
    parser = argparse.ArgumentParser(description="AIMAOS Standalone Desktop Application")
    parser.add_argument("--host", default=cfg.get("host", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(cfg.get("port", 8080)))
    parser.add_argument("--title", default="AIMAOS", help="Desktop window title")
    parser.add_argument("--no-daemon", action="store_true", help="Disable background office daemon")
    args = parser.parse_args(argv)

    print("=" * 68)
    print("AIMAOS DESKTOP WORKSTATION")
    print(f"Opening standalone app window: {args.title}")
    print("=" * 68)

    # Start server in background thread
    server_started = threading.Event()
    server_error = [None]

    def run_server():
        try:
            # We pass open_browser=False because we launch the app window explicitly below
            launch_aimaos_ui(
                port=args.port,
                host=args.host,
                open_browser=False,
                start_daemon=not args.no_daemon,
            )
        except Exception as exc:
            server_error[0] = exc

    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()

    time.sleep(1.0)
    if server_error[0]:
        print(f"[ERROR] Could not start AIMAOS server: {server_error[0]}", file=sys.stderr)
        return 1

    url = f"http://{args.host}:{args.port}"

    def on_window_close():
        print("[AIMAOS Desktop] App window closed by user. Shutting down.")
        os.kill(os.getpid(), signal.SIGINT)

    success = launch_desktop_window(url, title=args.title, on_close_callback=on_window_close)
    if not success:
        print(f"[AIMAOS Desktop] Standalone window launched url: {url}")

    try:
        while server_thread.is_alive():
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n[AIMAOS Desktop] Application exited.")

    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    raise SystemExit(main())

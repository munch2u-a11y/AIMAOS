"""Standalone desktop app window launcher for AIMAOS.

Launches the AIMAOS workstation UI in a chromeless, dedicated desktop application window
without browser tabs or URL bars, and manages clean shutdown on window exit.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
import logging
from typing import Callable

logger = logging.getLogger("aimaos.desktop")

KNOWN_CHROMIUM_BINARIES = [
    # Linux
    "google-chrome",
    "google-chrome-stable",
    "chromium",
    "chromium-browser",
    "microsoft-edge",
    "microsoft-edge-stable",
    "brave-browser",
    # macOS
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
    # Windows
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
]


def find_browser_binary() -> str | None:
    """Locate an available Chromium-based browser executable for app mode."""
    for binary in KNOWN_CHROMIUM_BINARIES:
        if os.path.isabs(binary):
            if os.path.isfile(binary) and os.access(binary, os.X_OK):
                return binary
        else:
            found = shutil.which(binary)
            if found:
                return found
    return None


def build_app_command(url: str, binary: str, *, user_data_dir: str | None = None, title: str = "AIMAOS") -> list[str]:
    """Construct the command line to launch the browser in chromeless app window mode."""
    cmd = [binary, f"--app={url}"]
    if user_data_dir:
        cmd.append(f"--user-data-dir={user_data_dir}")

    cmd.extend([
        "--no-first-run",
        "--no-default-browser-check",
        f"--window-name={title}",
    ])
    return cmd


def launch_desktop_window(
    url: str,
    *,
    title: str = "AIMAOS",
    on_close_callback: Callable[[], None] | None = None,
) -> bool:
    """Launch the AIMAOS UI inside a standalone desktop app window.

    Returns True if an app window process was successfully started.
    """
    # 1. Try PyWebView if available
    try:
        import webview
        logger.info("Launching desktop window via PyWebView...")
        window = webview.create_window(title, url, width=1280, height=820, resizable=True)
        if on_close_callback:
            window.events.closed += on_close_callback
        webview.start()
        return True
    except ImportError:
        pass
    except Exception as exc:
        logger.warning("PyWebView launch failed, falling back to Chromium app mode: %s", exc)

    # 2. Try Chromium App Mode (--app=URL)
    binary = find_browser_binary()
    if not binary:
        logger.warning("No Chromium-based browser found for app mode. Opening default browser.")
        import webbrowser
        webbrowser.open(url)
        return False

    cmd = build_app_command(url, binary, title=title)
    logger.info("Launching desktop app window: %s", " ".join(cmd))
    try:
        proc = subprocess.Popen(cmd)
        if on_close_callback:
            def monitor():
                proc.wait()
                on_close_callback()
            import threading
            threading.Thread(target=monitor, daemon=True).start()
        return True
    except Exception as exc:
        logger.error("Failed to launch desktop app window process: %s", exc)
        return False

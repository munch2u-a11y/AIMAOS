"""Tests for AIMAOS desktop app window launcher."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from core.desktop_launcher import build_app_command, find_browser_binary


class TestDesktopLauncher(unittest.TestCase):
    def test_find_browser_binary_returns_string_or_none(self):
        binary = find_browser_binary()
        if binary is not None:
            self.assertIsInstance(binary, str)
            self.assertTrue(len(binary) > 0)

    def test_build_app_command(self):
        url = "http://127.0.0.1:8080"
        binary = "/usr/bin/chromium"
        cmd = build_app_command(url, binary, title="AIMAOS")

        self.assertIn("/usr/bin/chromium", cmd)
        self.assertIn("--app=http://127.0.0.1:8080", cmd)
        self.assertIn("--window-name=AIMAOS", cmd)
        self.assertTrue(any(arg.startswith("--user-data-dir=") for arg in cmd))


if __name__ == "__main__":
    unittest.main()

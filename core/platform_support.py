"""Small host-platform helpers shared by setup, diagnostics, and agents."""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import Callable, Mapping


def user_config_dir(
    app_name: str = "aimaos",
    *,
    environ: Mapping[str, str] | None = None,
    platform_name: str | None = None,
) -> str:
    """Return the per-user configuration directory without creating it."""
    env = os.environ if environ is None else environ
    platform_name = os.name if platform_name is None else platform_name
    if platform_name == "nt":
        base = env.get("APPDATA") or env.get("LOCALAPPDATA")
        if not base:
            base = str(Path.home() / "AppData" / "Roaming")
    else:
        base = env.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return os.path.join(base, app_name)


def user_config_path(filename: str, app_name: str = "aimaos") -> str:
    return os.path.join(user_config_dir(app_name), filename)


def find_libreoffice(
    *,
    environ: Mapping[str, str] | None = None,
    platform_name: str | None = None,
    which: Callable[[str], str | None] = shutil.which,
) -> str | None:
    """Find LibreOffice on PATH or in common Windows installation folders."""
    for executable in ("soffice", "libreoffice"):
        found = which(executable)
        if found:
            return found

    env = os.environ if environ is None else environ
    platform_name = os.name if platform_name is None else platform_name
    if platform_name != "nt":
        return None

    roots = [env.get("ProgramFiles"), env.get("ProgramFiles(x86)"), env.get("LOCALAPPDATA")]
    candidates: list[Path] = []
    for root in filter(None, roots):
        base = Path(root)
        candidates.extend((
            base / "LibreOffice" / "program" / "soffice.exe",
            base / "Programs" / "LibreOffice" / "program" / "soffice.exe",
        ))
    return next((str(path) for path in candidates if path.is_file()), None)


def virtualenv_python(root: str | os.PathLike[str]) -> str:
    """Return the conventional virtual-environment interpreter for this host."""
    root_path = Path(root)
    relative = Path(".venv/Scripts/python.exe") if os.name == "nt" else Path(".venv/bin/python3")
    return str(root_path / relative)


def launch_command(script: str) -> str:
    """Return a copyable command using the active interpreter."""
    executable = os.path.basename(sys.executable) or ("python.exe" if os.name == "nt" else "python3")
    return f"{executable} {script}"

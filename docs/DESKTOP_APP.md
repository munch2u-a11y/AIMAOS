# AIMAOS Standalone Desktop Application

AIMAOS can run as a self-contained desktop application in its own chromeless OS window—with its own window title bar (`AIMAOS`), taskbar icon, and window controls—without requiring a web browser tab.

---

## Quick Start Launch

To launch AIMAOS in standalone desktop app mode:

```bash
.venv/bin/python3 aimaos_app.py
```

Or using the main CLI:

```bash
.venv/bin/python3 aimaos_ui.py --desktop
```

---

## How It Works

1. **Local Server & Daemon**: The local AIMAOS Python backend (`aimaos_ui.py`) and office daemon run locally bound to loopback (`127.0.0.1:8080`).
2. **Standalone App Window**: The workstation UI is rendered in a dedicated OS app window (using Chromium application mode `--app` or PyWebView native container).
3. **Clean Lifecycle**: Closing the desktop app window automatically stops the server and daemon processes cleanly.

---

## Desktop Launchers & Shortcuts

### Linux (`~/.local/share/applications/aimaos.desktop`)

Create a file named `aimaos.desktop`:

```ini
[Desktop Entry]
Name=AIMAOS
Comment=Private Office Copilot
Exec=/bin/bash -c "cd /path/to/AIMAOS && .venv/bin/python3 aimaos_app.py"
Terminal=false
Type=Application
Categories=Office;Utility;
```

### Windows Shortcut

Create a shortcut pointing to:

```cmd
C:\path\to\AIMAOS\.venv\Scripts\pythonw.exe aimaos_app.py
```

### macOS App Launcher

Run via terminal or wrap using Automator:

```bash
cd /path/to/AIMAOS && .venv/bin/python3 aimaos_app.py
```

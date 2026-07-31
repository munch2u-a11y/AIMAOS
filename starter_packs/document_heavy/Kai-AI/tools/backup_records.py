"""Mirrors the office's whole canonical records archive (client_file.py's
OUTPUT_ROOT) to a backup location outside any agent's own workspace, so
real client data survives even a wiped/regenerated agent directory
(agent workspaces aren't part of the git-tracked starter-pack material).

Uses rsync (already present on this system) rather than reimplementing a
mirror-with-deletion in pure Python -- it already handles incremental
copies and removing files/directories that no longer exist at the source
(e.g. a case moved by client_file.move_client_dir leaves its old location
empty; the backup should reflect that too, not accumulate stale copies).

Scheduling this (nightly, via Marley's daemon loop or otherwise) is a
separate decision -- this tool just does one backup pass when called.
"""
import os

def _find_aimaos_root():
    p = os.path.dirname(os.path.abspath(__file__))
    while p != os.path.dirname(p) and not os.path.exists(os.path.join(p, "aimaos_config.yaml")):
        p = os.path.dirname(p)
    return p
AIMAOS_ROOT = os.environ.get("AIMAOS_ROOT") or _find_aimaos_root()
import subprocess

OUTPUT_ROOT = os.path.join(AIMAOS_ROOT, "Alix-AI/workspace/output")
BACKUP_ROOT = os.path.expanduser("~/AIMAOS_records_backup")

TOOL_DEFINITION = {
    "name": "backup_records",
    "description": "Mirrors the office's whole canonical client/case records archive to a backup "
                   "location outside any single agent's workspace (via rsync -a --delete, so removed "
                   "or moved files are reflected too, not just new ones). Takes no arguments.",
    "parameters": {
        "type": "object",
        "properties": {},
        "required": []
    }
}


def execute():
    src = OUTPUT_ROOT.rstrip("/") + "/"
    dst = BACKUP_ROOT.rstrip("/") + "/"
    try:
        result = subprocess.run(
            ["rsync", "-a", "--delete", "--stats", src, dst],
            capture_output=True, text=True, timeout=300,
        )
    except FileNotFoundError:
        return "Error: rsync is not installed/available on this system; backup not performed."
    except subprocess.TimeoutExpired:
        return "Error: backup timed out after 300s; archive may be too large for this pass."

    if result.returncode != 0:
        return (f"Error: rsync exited {result.returncode}, backup may be incomplete.\n"
                f"{result.stderr.strip()[:500]}")

    stats_lines = [l for l in result.stdout.splitlines()
                   if l.startswith(("Number of", "Total file size"))]
    stats = "\n".join(stats_lines) if stats_lines else "(no stats reported)"
    return f"Backed up {OUTPUT_ROOT} -> {BACKUP_ROOT}.\n{stats}"

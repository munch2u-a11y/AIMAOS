"""Run the matter-local specialist through the shared digest-scoped service."""
import os
import sys


def _find_aimaos_root():
    path = os.path.dirname(os.path.abspath(__file__))
    while path != os.path.dirname(path) and not os.path.exists(os.path.join(path, "aimaos_config.yaml")):
        path = os.path.dirname(path)
    return path


AIMAOS_ROOT = os.environ.get("AIMAOS_ROOT") or _find_aimaos_root()
sys.path.insert(0, os.path.join(AIMAOS_ROOT, "Kai-AI"))
from business import client_file

sys.path.insert(0, AIMAOS_ROOT)
from core.case_specialist_service import refresh_case


def directory_listing(case_dir):
    """Compatibility helper retained for callers and older starter packs."""
    entries = []
    for root, directories, files in os.walk(case_dir):
        directories[:] = [name for name in directories if not name.startswith(".") and name != "__pycache__"]
        for name in files:
            if name in {"CLIENT_FILE.md", ".client_file_state.json"} or name.startswith("."):
                continue
            full = os.path.join(root, name)
            entries.append(f"- {os.path.relpath(full, case_dir)} ({os.path.getsize(full)} bytes)")
            if len(entries) >= 200:
                return "\n".join(entries) + "\n... (truncated)"
    return "\n".join(entries) if entries else "(directory is otherwise empty)"


def run_review_and_apply(client_name, *, force=True, reason="Kai case review"):
    if client_file.get_markdown(client_name) is None:
        return ([f"Error: no case record exists yet for {client_name}; use action=create first."], {})
    case_dir = client_file.resolve_client_dir(client_name)
    try:
        result = refresh_case(
            case_dir,
            client_name=client_name,
            force=force,
            reason=reason,
        )
    except Exception as exc:
        return ([f"Review failed for {client_name}: {exc}"], {})

    if result.get("status") == "unchanged":
        return ([f"Case agent for {client_name} found no file changes to review."], result)
    changed = ", ".join(result.get("overview_fields") or []) or "working overview metadata"
    report = [f"Case agent for {client_name} updated: {changed}."]
    for task in result.get("posted_tasks") or []:
        report.append(f"- Posted task {task.get('task_id')} to {task.get('agent')}: {task.get('title')}")
    for task in result.get("verification_tasks") or []:
        report.append(f"- Posted staff date-verification task {task.get('task_id')}: {task.get('date')}")
    report.extend(f"- Warning: {warning}" for warning in result.get("warnings") or [])
    return report, result

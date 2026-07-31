import os

def _find_aimaos_root():
    p = os.path.dirname(os.path.abspath(__file__))
    while p != os.path.dirname(p) and not os.path.exists(os.path.join(p, "aimaos_config.yaml")):
        p = os.path.dirname(p)
    return p
AIMAOS_ROOT = os.environ.get("AIMAOS_ROOT") or _find_aimaos_root()
import sys
import shutil
import yaml
import importlib.util
from datetime import datetime

sys.path.insert(0, os.path.join(AIMAOS_ROOT, "Alix-AI"))
from business.watchers.email_connector import EmailConnector

# Kai owns case-record organization now — loaded by file path (not
# `sys.path.insert` + package import) because Kai-AI also has its own
# "business" package; inserting both on sys.path would collide, exactly
# like the core/ package collision this convention was created to avoid.
_client_file_spec = importlib.util.spec_from_file_location(
    "kai_client_file", os.path.join(AIMAOS_ROOT, "Kai-AI/business/client_file.py"))
client_file = importlib.util.module_from_spec(_client_file_spec)
_client_file_spec.loader.exec_module(client_file)

TOOL_DEFINITION = {
    "name": "dispatch_document",
    "description": "Archives a generated document into a designated client folder and dispatches it via email or local cloud sync (Dropbox/Google Drive).",
    "parameters": {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Path to the generated .docx or .pdf document file."
            },
            "client_name": {
                "type": "string",
                "description": "Name of the client (e.g. 'Bob Client'). Used to structure output folders."
            },
            "recipient_email": {
                "type": "string",
                "description": "Optional email address to send the document to."
            },
            "notes": {
                "type": "string",
                "description": "Optional message or summary note for the client."
            }
        },
        "required": ["file_path", "client_name"]
    }
}

def get_config():
    tools_dir = os.path.dirname(os.path.abspath(__file__))
    project_dir = os.path.dirname(tools_dir)
    config_path = os.path.join(project_dir, "config.yaml")
    if os.path.exists(config_path):
        with open(config_path, "r") as f:
            try:
                return yaml.safe_load(f)
            except Exception:
                pass
    return {}

def execute(file_path, client_name, recipient_email=None, notes=None):
    abs_file = os.path.abspath(file_path)
    if not os.path.exists(abs_file):
        return f"Error: File to dispatch does not exist at {abs_file}"

    config = get_config()

    # Kai organizes/owns where a client's record actually lives (by matter
    # type, by branch, whatever fits — see Kai's manage_case_records); defer
    # to that instead of deciding a flat path here. Falls back to creating
    # an uncategorized record if Kai hasn't organized this client yet.
    client_root = client_file.resolve_client_dir(client_name)
    date_str = datetime.now().strftime("%Y-%m-%d")
    client_archive_dir = os.path.join(client_root, date_str)
    os.makedirs(client_archive_dir, exist_ok=True)

    dest_file = os.path.join(client_archive_dir, os.path.basename(abs_file))
    if abs_file != dest_file:
        shutil.copy2(abs_file, dest_file)

    # Keep the client's case file current automatically — the checklist and
    # activity log shouldn't depend on the agent remembering a second call.
    client_file.mark_document_dispatched(client_name, os.path.basename(dest_file), dest_file)

    response_lines = [
        f"Success: Document archived for client '{client_name}'.",
        f"- Archived Path: {dest_file}"
    ]

    # Handle Email dispatch if recipient provided
    if recipient_email:
        email_conn = EmailConnector(config.get("email", {}))
        subject = f"Document Completed for {client_name}"
        body = notes or f"Hello,\n\nPlease find your requested document attached ({os.path.basename(dest_file)}).\n\nBest regards,\nAlix-AI Document Agent"
        sent_ok, send_msg = email_conn.send_document(recipient_email, subject, body, dest_file)
        if sent_ok:
            response_lines.append(f"- Email Dispatch: {send_msg}")
        else:
            response_lines.append(f"- Email Dispatch Notice: {send_msg}")

    return "\n".join(response_lines)

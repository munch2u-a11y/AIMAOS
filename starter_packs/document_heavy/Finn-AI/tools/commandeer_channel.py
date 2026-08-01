import os

def _find_aimaos_root():
    p = os.path.dirname(os.path.abspath(__file__))
    while p != os.path.dirname(p) and not os.path.exists(os.path.join(p, "aimaos_config.yaml")):
        p = os.path.dirname(p)
    return p
AIMAOS_ROOT = os.environ.get("AIMAOS_ROOT") or _find_aimaos_root()
import sys
import json
import importlib.util
from datetime import datetime

sys.path.insert(0, AIMAOS_ROOT)
sys.path.insert(0, os.path.join(AIMAOS_ROOT, "Alix-AI"))
from business.watchers.email_connector import EmailConnector

# Kai owns case-record organization — loaded by file path, not `sys.path.insert`
# + package import, same reason as Alix's dispatch_document.py (Kai-AI's
# `business` package is a namespace package that would collide otherwise).
_client_file_spec = importlib.util.spec_from_file_location(
    "kai_client_file", os.path.join(AIMAOS_ROOT, "Kai-AI/business/client_file.py"))
client_file = importlib.util.module_from_spec(_client_file_spec)
_client_file_spec.loader.exec_module(client_file)

CREDENTIALS_ENV_PATH = os.path.expanduser("~/.config/aimaos/credentials.env")
TELEGRAM_ENV_PATH = os.path.expanduser("~/.config/aimaos/telegram.env")

TOOL_DEFINITION = {
    "name": "commandeer_channel",
    "description": "Allows an active agent (Alix, Quinn, Marley) to commandeer Finn's communication gateway to send outbound messages, Telegram updates, or client email packages. Pass client_name when this delivery is for a specific client's matter so the case's own activity log reflects that it was actually sent.",
    "parameters": {
        "type": "object",
        "properties": {
            "calling_agent": {
                "type": "string",
                "description": "Agent commandeering the channel (e.g. 'Alix', 'Quinn', 'Marley')."
            },
            "recipient_email": {
                "type": "string",
                "description": "Destination email address (e.g. 'client@example.com')."
            },
            "subject": {
                "type": "string",
                "description": "Email or message subject line."
            },
            "body": {
                "type": "string",
                "description": "Full text body of the outbound communication."
            },
            "attachments": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of file paths to attach (e.g. generated court .docx / .pdf files)."
            },
            "client_name": {
                "type": "string",
                "description": "Optional: give this whenever the message is for a specific client's "
                               "matter — must match what other agents use (populate_template, "
                               "dispatch_document, manage_case_records) so a successful send is logged "
                               "into that same case's activity log, not just the global outbound log."
            }
        },
        "required": ["calling_agent", "recipient_email", "subject", "body"]
    }
}

def load_helix_credentials():
    """Loads Helix credentials from environment files."""
    for path in [CREDENTIALS_ENV_PATH, TELEGRAM_ENV_PATH]:
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, v = line.split("=", 1)
                            if k.strip() not in os.environ:
                                os.environ[k.strip()] = v.strip().strip('"').strip("'")
            except Exception:
                pass

def execute(calling_agent, recipient_email, subject, body, attachments=None, client_name=None):
    load_helix_credentials()

    # Send email package
    connector = EmailConnector()
    res = connector.send_email(
        recipient=recipient_email,
        subject=f"[{calling_agent} via Finn Gateway] {subject}",
        body=body,
        attachments=attachments or []
    )

    # Check Telegram and Discord tokens status (without exposing secrets)
    has_telegram = bool(os.environ.get("HELIX_TELEGRAM_TOKEN") or os.environ.get("MRAG_TELEGRAM_TOKEN"))
    has_discord = bool(os.environ.get("HELIX_DISCORD_TOKEN"))

    comms_status = f"Comms Channels Active: Email ({connector.username})"
    if has_telegram:
        comms_status += " | Telegram Bot Gateway (Configured)"
    if has_discord:
        comms_status += " | Discord Bot Gateway (Configured)"

    delivered = ": DISPATCHED (" in res.upper()
    case_note = ""
    if client_name and delivered and client_file.client_exists(client_name):
        client_file.log_entry(
            client_name, f"Finn sent '{subject}' to {recipient_email} on behalf of {calling_agent}.")
        case_note = f"\n- Filed in case record for {client_name}"

    outcome = "dispatched" if delivered else "not dispatched"
    return (f"Finn Gateway: Channel request by {calling_agent} was {outcome}.\n"
            f"- Channel Status: {comms_status}\n- Result: {res}{case_note}")

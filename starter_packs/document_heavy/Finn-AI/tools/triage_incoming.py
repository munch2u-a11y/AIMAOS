import os

def _find_aimaos_root():
    p = os.path.dirname(os.path.abspath(__file__))
    while p != os.path.dirname(p) and not os.path.exists(os.path.join(p, "aimaos_config.yaml")):
        p = os.path.dirname(p)
    return p
AIMAOS_ROOT = os.environ.get("AIMAOS_ROOT") or _find_aimaos_root()
import sys
import json

sys.path.insert(0, AIMAOS_ROOT)
from core.comms.office_board import OfficeBoard

TOOL_DEFINITION = {
    "name": "triage_incoming",
    "description": "Performs security verification and priority classification on unsolicited incoming messages, logging validated requests to the Office Board.",
    "parameters": {
        "type": "object",
        "properties": {
            "sender_address": {
                "type": "string",
                "description": "Email address or username of the incoming sender."
            },
            "channel": {
                "type": "string",
                "description": "Communication channel ('email', 'web_ui', 'discord', 'telegram', 'whatsapp')."
            },
            "message": {
                "type": "string",
                "description": "Raw incoming message content."
            }
        },
        "required": ["sender_address", "message"]
    }
}

def execute(sender_address, message, channel="email"):
    board = OfficeBoard()
    msg_lower = message.lower()

    # Security check: the sender's actual domain must be on the allowlist, or sent via web_ui workstation.
    allowed_domains = ["gmail.com", "court.fl.gov", "lawfirm.com", "localhost", "example.com"]
    sender_domain = sender_address.rsplit("@", 1)[-1].lower().strip()
    is_verified = (channel == "web_ui") or any(sender_domain == d or sender_domain.endswith("." + d) for d in allowed_domains)

    target_agent = "Alix"
    intent = "document_request"

    if "research" in msg_lower or "statute" in msg_lower or "case law" in msg_lower:
        target_agent = "Quinn"
        intent = "legal_research"
    elif "schedule" in msg_lower or "hearing" in msg_lower or "deadline" in msg_lower:
        target_agent = "Marley"
        intent = "scheduling"

    task_id = board.post_task(
        title=f"[{channel.upper()}] {intent.replace('_', ' ').title()} from {sender_address}",
        requester=sender_address,
        target_agent=target_agent,
        priority="HIGH" if is_verified else "NORMAL",
        details={
            "channel": channel,
            "sender": sender_address,
            "message": message,
            "security_status": "VERIFIED" if is_verified else "UNVERIFIED"
        }
    )

    return f"Finn Security Officer: Triaged incoming message from {sender_address} via {channel}.\n- Security Status: {'VERIFIED' if is_verified else 'UNVERIFIED'}\n- Assigned Agent: {target_agent}\n- Posted Task ID: {task_id}"

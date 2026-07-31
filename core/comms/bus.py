import os

def _find_aimaos_root():
    p = os.path.dirname(os.path.abspath(__file__))
    while p != os.path.dirname(p) and not os.path.exists(os.path.join(p, "aimaos_config.yaml")):
        p = os.path.dirname(p)
    return p
AIMAOS_ROOT = os.environ.get("AIMAOS_ROOT") or _find_aimaos_root()
import json
import time
import glob
import logging
from datetime import datetime
from core.atomic_io import atomic_write_json
from core.security import validate_agent_name

logger = logging.getLogger(__name__)

COMMS_BASE_DIR = os.path.join(AIMAOS_ROOT, "comms")

class AgentCompanyBus:
    """
    Lightweight, 100% offline file-queue IPC communication bus for AIMAOS.
    Enables Alix, Kai, Marley, Quinn, Zoe, and clones to send, query, and receive messages.
    """
    def __init__(self, agent_name):
        self.agent_name = validate_agent_name(agent_name)
        self.inbox_dir = os.path.join(COMMS_BASE_DIR, agent_name, "inbox")
        self.outbox_dir = os.path.join(COMMS_BASE_DIR, agent_name, "outbox")
        
        os.makedirs(self.inbox_dir, exist_ok=True)
        os.makedirs(self.outbox_dir, exist_ok=True)

    def send_message(self, recipient, action, payload):
        """Sends an inter-agent message to recipient's inbox."""
        recipient = validate_agent_name(recipient)
        msg_id = f"msg_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
        recipient_inbox = os.path.join(COMMS_BASE_DIR, recipient, "inbox")
        os.makedirs(recipient_inbox, exist_ok=True)

        envelope = {
            "id": msg_id,
            "sender": self.agent_name,
            "recipient": recipient,
            "action": action,
            "payload": payload,
            "timestamp": datetime.now().isoformat(),
            "status": "pending"
        }

        # Write to recipient inbox
        target_path = os.path.join(recipient_inbox, f"{msg_id}.json")
        atomic_write_json(target_path, envelope)

        # Write copy to sender outbox
        outbox_path = os.path.join(self.outbox_dir, f"{msg_id}.json")
        atomic_write_json(outbox_path, envelope)

        logger.info(f"[{self.agent_name}] Sent message {msg_id} to {recipient} (action: {action})")
        return msg_id

    def read_inbox(self, mark_read=True):
        """Reads all pending incoming messages from inbox."""
        messages = []
        files = sorted(glob.glob(os.path.join(self.inbox_dir, "*.json")))
        for fpath in files:
            try:
                with open(fpath, "r") as f:
                    data = json.load(f)
                    messages.append(data)
                if mark_read:
                    read_path = fpath.replace(".json", ".read")
                    os.rename(fpath, read_path)
            except Exception as e:
                logger.error(f"Error reading message {fpath}: {e}")
        return messages

    def reply_message(self, original_msg, reply_payload):
        """Replies to an incoming message."""
        sender = validate_agent_name(original_msg["sender"])
        msg_id = original_msg["id"]
        sender_inbox = os.path.join(COMMS_BASE_DIR, sender, "inbox")
        os.makedirs(sender_inbox, exist_ok=True)

        reply_envelope = {
            "id": f"reply_{msg_id}",
            "reply_to": msg_id,
            "sender": self.agent_name,
            "recipient": sender,
            "action": f"reply_{original_msg.get('action')}",
            "payload": reply_payload,
            "timestamp": datetime.now().isoformat()
        }

        reply_path = os.path.join(sender_inbox, f"reply_{msg_id}.json")
        atomic_write_json(reply_path, reply_envelope)

        return f"Replied to {sender} for {msg_id}."

    def ask_peer_and_wait(self, recipient, action, payload, timeout=8.0, poll_interval=0.3):
        """Sends a message and polls this agent's own inbox for the matching
        reply until timeout. Only resolves if something is actually
        processing the recipient's inbox during that window (the office
        daemon's regular pulse, or another agent's turn) — this is a file
        queue, not a live RPC call, so a recipient that isn't currently
        running its own inbox-processing loop will simply time out."""
        msg_id = self.send_message(recipient, action, payload)
        reply_path = os.path.join(self.inbox_dir, f"reply_{msg_id}.json")
        deadline = time.time() + timeout
        while time.time() < deadline:
            if os.path.exists(reply_path):
                with open(reply_path, "r") as f:
                    reply = json.load(f)
                os.rename(reply_path, reply_path.replace(".json", ".read"))
                return reply.get("payload")
            time.sleep(poll_interval)
        return {"status": "timeout", "result": f"No reply from {recipient} within {timeout}s"}

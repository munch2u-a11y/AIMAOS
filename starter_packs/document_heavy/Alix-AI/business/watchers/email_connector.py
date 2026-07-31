import os

def _find_aimaos_root():
    p = os.path.dirname(os.path.abspath(__file__))
    while p != os.path.dirname(p) and not os.path.exists(os.path.join(p, "aimaos_config.yaml")):
        p = os.path.dirname(p)
    return p
AIMAOS_ROOT = os.environ.get("AIMAOS_ROOT") or _find_aimaos_root()
import json
import logging
import yaml
from datetime import datetime

logger = logging.getLogger(__name__)

CREDENTIALS_ENV_PATH = os.path.expanduser("~/.config/aimaos/credentials.env")
CONFIG_PATH = os.path.join(AIMAOS_ROOT, "aimaos_config.yaml")
OUTBOUND_LOG_FILE = os.path.join(AIMAOS_ROOT, "Alix-AI/workspace/output/outbound_email_log.json")
INBOUND_ATTACHMENTS_DIR = os.path.join(AIMAOS_ROOT, "Finn-AI/workspace/inbound_emails")

def load_credentials_env():
    """Safely loads key-value pairs from credentials.env into os.environ if present."""
    if os.path.exists(CREDENTIALS_ENV_PATH):
        try:
            with open(CREDENTIALS_ENV_PATH, "r") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        if k.strip() not in os.environ:
                            os.environ[k.strip()] = v.strip().strip('"').strip("'")
        except Exception as e:
            logger.warning(f"Could not load credentials env: {e}")

def load_office_config():
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r") as f:
                return yaml.safe_load(f) or {}
        except Exception:
            pass
    return {}

class SecurityPolicyException(Exception):
    """Raised when an outbound email violates system security policies."""
    pass

class EmailConnector:
    """
    Email Connector interface for Alix-AI / AIMAOS / Finn-AI.
    Provides inbound IMAP polling & attachment extraction, and hardware-enforced outbound SMTP controls.
    """
    def __init__(self, config=None):
        load_credentials_env()
        office_cfg = load_office_config()
        self.config = config or office_cfg.get("email", {})
        
        self.security_mode = os.environ.get(
            "AIMAOS_EMAIL_SECURITY_MODE", 
            self.config.get("security_mode", "READ_ONLY")
        ).upper()
        
        self.approved_recipients = set(
            self.config.get("approved_recipients", [])  # deny-all until the operator whitelists recipients
        )
        
        self.smtp_server = os.environ.get("HELIX_SMTP_SERVER", self.config.get("smtp_server", "smtp.gmail.com"))
        self.smtp_port = int(os.environ.get("HELIX_SMTP_PORT", self.config.get("smtp_port", 587)))
        self.imap_server = os.environ.get("HELIX_IMAP_SERVER", self.config.get("imap_server", "imap.gmail.com"))
        self.imap_port = int(os.environ.get("HELIX_IMAP_PORT", self.config.get("imap_port", 993)))
        
        self.username = os.environ.get("HELIX_EMAIL_USER", self.config.get("username", "office@example.com"))
        self.password = os.environ.get("HELIX_EMAIL_PASS", self.config.get("password", ""))

    def check_outbound_policy(self, recipient):
        """Hardware-enforces email security policies before any SMTP connection is initialized."""
        if self.security_mode == "READ_ONLY":
            msg = f"SECURITY POLICY BLOCKED: READ_ONLY mode is active. Outbound emails are disabled system-wide. Cannot email '{recipient}'."
            logger.warning(msg)
            raise SecurityPolicyException(msg)
            
        if self.security_mode == "WHITELIST_ONLY":
            if recipient.lower() not in [r.lower() for r in self.approved_recipients]:
                msg = f"SECURITY POLICY BLOCKED: Recipient '{recipient}' is not in approved whitelist {list(self.approved_recipients)}. Dispatch denied."
                logger.warning(msg)
                raise SecurityPolicyException(msg)
                
        if self.security_mode == "DISABLED":
            msg = "SECURITY POLICY BLOCKED: Email subsystem is completely DISABLED."
            logger.warning(msg)
            raise SecurityPolicyException(msg)
            
        return True

    def _smtp_send(self, recipient, subject, body, attachments):
        """Performs an actual SMTP dispatch. Raises on failure."""
        import smtplib
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText
        from email.mime.application import MIMEApplication

        msg = MIMEMultipart()
        msg["From"] = self.username
        msg["To"] = recipient
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        for fpath in attachments:
            if os.path.exists(fpath):
                with open(fpath, "rb") as f:
                    part = MIMEApplication(f.read(), Name=os.path.basename(fpath))
                part["Content-Disposition"] = f'attachment; filename="{os.path.basename(fpath)}"'
                msg.attach(part)

        with smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=30) as server:
            server.starttls()
            server.login(self.username, self.password)
            server.send_message(msg)

    def send_email(self, recipient, subject, body, attachments=None):
        """
        Dispatches an outbound client email package subject to strict security checks.
        """
        attachments = attachments or []
        os.makedirs(os.path.dirname(OUTBOUND_LOG_FILE), exist_ok=True)

        # 1. Enforce Outbound Security Policy
        try:
            self.check_outbound_policy(recipient)
        except SecurityPolicyException as spe:
            self._log_dispatch(recipient, subject, body, attachments, "BLOCKED_BY_POLICY", str(spe))
            return str(spe)

        # 2. Check SMTP configuration
        smtp_enabled = os.environ.get("AIMAOS_SMTP_SEND") == "1" and bool(self.password)
        status = "SIMULATED"
        detail = "offline mode: package logged locally, no SMTP dispatch attempted"
        if smtp_enabled:
            try:
                self._smtp_send(recipient, subject, body, attachments)
                status = "DISPATCHED"
                detail = f"SMTP dispatch via {self.smtp_server}:{self.smtp_port}"
            except Exception as e:
                status = "FAILED"
                detail = f"SMTP dispatch failed: {e}"
                logger.error(detail)

        self._log_dispatch(recipient, subject, body, attachments, status, detail)
        logger.info(f"Email package to {recipient} (Subject: {subject}) -> {status}")
        return f"Email package from '{self.username}' to '{recipient}' with {len(attachments)} attachment(s): {status} ({detail})."

    def _log_dispatch(self, recipient, subject, body, attachments, status, detail):
        entry = {
            "id": f"mail_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}",
            "sender_account": self.username,
            "recipient": recipient,
            "subject": subject,
            "body": body,
            "attachments": attachments,
            "security_mode": self.security_mode,
            "timestamp": datetime.now().isoformat(),
            "status": status,
            "detail": detail
        }

        logs = []
        if os.path.exists(OUTBOUND_LOG_FILE):
            try:
                with open(OUTBOUND_LOG_FILE, "r") as f:
                    logs = json.load(f)
            except Exception:
                pass
        logs.append(entry)
        with open(OUTBOUND_LOG_FILE, "w") as f:
            json.dump(logs, f, indent=2)

    def fetch_inbound_emails(self, max_messages=10):
        """
        Polls inbound company email mailbox via IMAP, extracts message bodies and attachments,
        saves attachments to Finn's inbound queue, and logs incoming records for Kai/Finn.
        """
        import imaplib
        import email
        from email.header import decode_header

        os.makedirs(INBOUND_ATTACHMENTS_DIR, exist_ok=True)

        if not self.password:
            logger.info("IMAP polling skipped: No email password configured in environment or credentials.")
            return {"status": "SKIPPED", "reason": "No password configured", "inbound_count": 0, "attachments_saved": []}

        inbound_records = []
        saved_attachments = []

        try:
            mail = imaplib.IMAP4_SSL(self.imap_server, self.imap_port)
            mail.login(self.username, self.password)
            mail.select("INBOX")

            status, messages = mail.search(None, 'UNSEEN')
            if status != "OK":
                mail.logout()
                return {"status": "OK", "inbound_count": 0, "attachments_saved": []}

            email_ids = messages[0].split()
            for e_id in email_ids[-max_messages:]:
                res, msg_data = mail.fetch(e_id, '(RFC822)')
                if res != "OK":
                    continue

                for response_part in msg_data:
                    if isinstance(response_part, tuple):
                        msg = email.message_from_bytes(response_part[1])
                        subject, encoding = decode_header(msg.get("Subject", ""))[0]
                        if isinstance(subject, bytes):
                            subject = subject.decode(encoding or "utf-8", errors="replace")
                        sender = msg.get("From", "")

                        body = ""
                        if msg.is_multipart():
                            for part in msg.walk():
                                c_type = part.get_content_type()
                                c_disp = str(part.get("Content-Disposition"))
                                if c_type == "text/plain" and "attachment" not in c_disp:
                                    body = part.get_payload(decode=True).decode(errors="replace")
                                elif "attachment" in c_disp:
                                    filename = part.get_filename()
                                    if filename:
                                        att_path = os.path.join(INBOUND_ATTACHMENTS_DIR, f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{filename}")
                                        with open(att_path, "wb") as f:
                                            f.write(part.get_payload(decode=True))
                                        saved_attachments.append(att_path)
                        else:
                            body = msg.get_payload(decode=True).decode(errors="replace")

                        record = {
                            "id": f"inbound_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}",
                            "sender": sender,
                            "subject": subject,
                            "body": body[:500],
                            "attachments": saved_attachments,
                            "received_at": datetime.now().isoformat()
                        }
                        inbound_records.append(record)

            mail.logout()
        except Exception as e:
            logger.error(f"Inbound IMAP fetch error: {e}")
            return {"status": "ERROR", "reason": str(e), "inbound_count": 0, "attachments_saved": []}

        return {
            "status": "SUCCESS",
            "inbound_count": len(inbound_records),
            "attachments_saved": saved_attachments,
            "records": inbound_records
        }

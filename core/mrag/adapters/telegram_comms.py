"""Telegram comms for the autonomous agent — reach out, under guardrails.

The capability that made the long-running Helix instance feel alive was
initiating contact: messaging its person unprompted when it had
something to say. This module ports that, with the trust boundary in
the harness instead of the model. A 4-9B model running unattended does
NOT get an open messaging channel; it gets:

- A contact allowlist (name → chat id). Only listed chats can be
  messaged or heard from; everything else is dropped at this layer.
- An OutboundGovernor: a hard per-hour send cap plus quiet hours.
  Refusals are returned to the model as tool errors, so it learns the
  rules exist without being able to bend them.
- Incoming messages go through a callback (wire it to
  PulseLoop.post_event) so a Telegram ping wakes the agent into ACTIVE.

Zero external dependencies: the Bot API is plain HTTPS long-polling via
urllib. The polling thread is owned by the harness (start_polling /
stop_polling), consistent with the pulse loop owning no threads itself.

Setup: create a bot with @BotFather, put the token in
MRAG_TELEGRAM_TOKEN, message the bot once from each allowed account,
and read the chat ids from get_recent_chat_ids() (or the daemon's
--telegram-setup flag, which prints them).
"""

import json
import logging
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import deque
from datetime import datetime
from typing import Any, Callable, Dict, Optional, Tuple

from mrag.adapters.tool_groups import Tool, ToolGroup
from mrag.adapters.pulse_loop import _parse_clock

logger = logging.getLogger("mrag.adapters.telegram_comms")

_API = "https://api.telegram.org"


class OutboundGovernor:
    """Rate cap + quiet hours for anything the agent sends outward.

    Shared across channels on purpose: the cap bounds total outbound
    chatter, not per-channel chatter."""

    def __init__(self, max_per_hour: int = 4,
                 quiet_start: str = "23:30", quiet_end: str = "07:30",
                 clock: Callable[[], datetime] = datetime.now):
        self.max_per_hour = max_per_hour
        self.quiet_start = quiet_start
        self.quiet_end = quiet_end
        self.clock = clock
        self._sends: deque = deque()
        self._lock = threading.Lock()
        # Monotonic count of everything ever sent — the ground truth for
        # send-claim verification (the deque above gets pruned).
        self.total_sends = 0

    def _in_quiet_hours(self, now: datetime) -> bool:
        start_h, start_m = _parse_clock(self.quiet_start)
        end_h, end_m = _parse_clock(self.quiet_end)
        start = now.replace(hour=start_h, minute=start_m, second=0, microsecond=0)
        end = now.replace(hour=end_h, minute=end_m, second=0, microsecond=0)
        if start == end:
            return False
        if start < end:
            return start <= now < end
        return now >= start or now < end

    def check(self, now: Optional[datetime] = None) -> Tuple[bool, str]:
        """(allowed, reason). Does not record a send — call record()
        after the send actually succeeds."""
        now = now or self.clock()
        if self._in_quiet_hours(now):
            return False, (f"quiet hours ({self.quiet_start}-{self.quiet_end}): "
                           "no outbound messages; leave yourself a schedule "
                           "reminder to send it in the morning instead")
        with self._lock:
            cutoff = now.timestamp() - 3600
            while self._sends and self._sends[0] < cutoff:
                self._sends.popleft()
            if len(self._sends) >= self.max_per_hour:
                return False, (f"outbound cap reached ({self.max_per_hour}/hour); "
                               "wait or schedule it for later")
        return True, ""

    def record(self, now: Optional[datetime] = None):
        now = now or self.clock()
        with self._lock:
            self._sends.append(now.timestamp())
            self.total_sends += 1


class TelegramComms:
    """Allowlisted Telegram Bot API client: send + long-poll receive."""

    def __init__(self, token: str, contacts: Dict[str, str],
                 governor: Optional[OutboundGovernor] = None,
                 request_timeout: int = 65):
        """contacts: display name → chat id (str). The model addresses
        people by name; raw chat ids never enter its context."""
        self.token = token
        self.contacts = {name: str(chat_id) for name, chat_id in contacts.items()}
        self.governor = governor or OutboundGovernor()
        self.request_timeout = request_timeout
        self._offset = 0
        self._polling = False
        self._poll_thread: Optional[threading.Thread] = None

    def _call(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{_API}/bot{self.token}/{method}"
        data = urllib.parse.urlencode(params).encode("utf-8")
        request = urllib.request.Request(url, data=data)
        with urllib.request.urlopen(request, timeout=self.request_timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    # ── outbound ─────────────────────────────────────────────────────

    def send(self, contact: str, text: str) -> str:
        contact = (contact or "").strip()
        text = (text or "").strip()
        if not text:
            return "ERROR: message text is required."
        chat_id = self.contacts.get(contact)
        if chat_id is None:
            known = ", ".join(sorted(self.contacts)) or "none configured"
            return f"ERROR: '{contact}' is not an allowed contact. Contacts: {known}."
        allowed, reason = self.governor.check()
        if not allowed:
            return f"ERROR: not sent — {reason}."
        try:
            result = self._call("sendMessage", {"chat_id": chat_id, "text": text[:4000]})
        except (urllib.error.URLError, OSError, json.JSONDecodeError) as e:
            return f"ERROR: Telegram send failed: {e}"
        if not result.get("ok"):
            return f"ERROR: Telegram refused: {result.get('description', 'unknown')}"
        self.governor.record()
        logger.info(f"Telegram → {contact}: {text[:80]}")
        return f"ok, sent to {contact}."

    def list_contacts(self) -> str:
        if not self.contacts:
            return "No contacts configured."
        return "Allowed contacts: " + ", ".join(sorted(self.contacts))

    # ── inbound ──────────────────────────────────────────────────────

    def _allowed_chat(self, chat_id: str) -> Optional[str]:
        for name, allowed_id in self.contacts.items():
            if allowed_id == str(chat_id):
                return name
        return None

    def poll_once(self, on_message: Callable[[str, str], None],
                  timeout: int = 50) -> int:
        """One long-poll getUpdates call. on_message(text, sender_name)
        fires per allowed incoming message; others are dropped (and
        logged) here, before the model ever sees them. Returns the
        number of messages delivered."""
        try:
            result = self._call("getUpdates", {"offset": self._offset + 1,
                                               "timeout": timeout})
        except (urllib.error.URLError, OSError, json.JSONDecodeError) as e:
            logger.warning(f"Telegram poll failed: {e}")
            return 0
        delivered = 0
        for update in result.get("result", []):
            self._offset = max(self._offset, update.get("update_id", 0))
            message = update.get("message") or {}
            text = (message.get("text") or "").strip()
            chat_id = str((message.get("chat") or {}).get("id", ""))
            if not text or not chat_id:
                # Voice notes, photos, stickers, edits, reactions: the
                # update is consumed (and thereby confirmed to Telegram)
                # even though nothing is delivered — say so in the log,
                # or these vanish without a trace.
                kinds = [k for k in update if k != "update_id"]
                logger.info(f"Skipped non-text update {update.get('update_id')} "
                            f"({', '.join(kinds) or 'unknown type'})")
                continue
            sender = self._allowed_chat(chat_id)
            if sender is None:
                logger.info(f"Dropped message from non-allowlisted chat {chat_id}")
                continue
            on_message(text, sender)
            delivered += 1
        return delivered

    def start_polling(self, on_message: Callable[[str, str], None]):
        if self._polling:
            return
        self._polling = True

        def _loop():
            # The loop must be unkillable: poll_once catches the common
            # network errors, but urllib can also raise HTTPException
            # subclasses (IncompleteRead on a dropped long-poll, etc.) —
            # one uncaught exception here silently severs the agent's
            # only inbound channel until the next process restart.
            while self._polling:
                try:
                    self.poll_once(on_message)
                except Exception as e:
                    logger.error(f"Telegram poll loop error (recovering): {e}")
                    time.sleep(5)

        self._poll_thread = threading.Thread(target=_loop, daemon=True,
                                             name="mrag_telegram_poll")
        self._poll_thread.start()

    def stop_polling(self):
        self._polling = False

    def get_recent_chat_ids(self) -> str:
        """Setup helper: chat ids of whoever has messaged the bot, for
        building the allowlist. Not exposed to the model."""
        try:
            result = self._call("getUpdates", {"timeout": 0})
        except (urllib.error.URLError, OSError, json.JSONDecodeError) as e:
            return f"ERROR: {e}"
        seen = {}
        for update in result.get("result", []):
            message = update.get("message") or {}
            chat = message.get("chat") or {}
            if chat.get("id"):
                who = chat.get("username") or chat.get("first_name") or "?"
                seen[str(chat["id"])] = who
        if not seen:
            return "No messages yet — have each contact message the bot once."
        return "\n".join(f"{chat_id}  ({who})" for chat_id, who in seen.items())


def build_telegram_group(comms: TelegramComms) -> ToolGroup:
    return ToolGroup(
        name="telegram",
        summary="send Telegram messages to allowed contacts",
        tools=[
            Tool("send_telegram",
                 "Send a Telegram message to an allowed contact (rate-capped; "
                 "blocked during quiet hours).",
                 handler=comms.send,
                 parameters={
                     "contact": "string, contact name from the allowlist",
                     "text": "string, the message to send",
                 },
                 informational=False),
            Tool("list_telegram_contacts", "The contacts you are allowed to message.",
                 handler=comms.list_contacts, parameters={}),
        ],
    )

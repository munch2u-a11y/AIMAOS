"""Starter suite of commonly relied-on agent tools.

Ready-made ToolGroups for the orchestrated tool pipeline, sized to the
1-5-tools-per-subagent rule; the email suite exceeds that and ships as a
CompositeToolGroup — a sub-orchestrator divides it into read/write
subgroups. Everything is standard library only (imaplib/smtplib, urllib,
subprocess) so the suite adds zero dependencies.

Handlers are configured by environment variables and return a clear
"CONFIG ERROR: ..." string when unconfigured — a string, not an
exception, so the subagent can report the gap instead of crashing.

| Group    | Tools | Config |
| email    | read: search_inbox, read_email, mark_read / write: send_email, reply_email | MRAG_EMAIL_ADDRESS + MRAG_EMAIL_PASSWORD (app password; GMAIL_ADDRESS/GMAIL_APP_PASSWORD honored), MRAG_IMAP_HOST / MRAG_SMTP_HOST (default Gmail) |
| telegram | telegram_send, telegram_updates | TELEGRAM_BOT_TOKEN (or HELIX_TELEGRAM_TOKEN), TELEGRAM_CHAT_ID (or TELEGRAM_OWNER_ID) |
| discord  | discord_send | DISCORD_WEBHOOK_URL |
| web      | web_search, read_url | BRAVE_API_KEY (optional; DuckDuckGo HTML fallback) |
| files    | read_file, write_file, append_file, list_dir, search_files | MRAG_FILES_ROOT (default cwd) |
| notes    | save_note, list_notes, complete_note | MRAG_NOTES_PATH (default ~/.mrag_notes.json) |
| schedule | add_event, list_schedule, due_reminders, cancel_entry | MRAG_SCHEDULE_PATH (default ~/.mrag_schedule.json) |
| shell    | run_command (opt-in: include_shell=True) | MRAG_FILES_ROOT as cwd |
"""

import html as html_lib
import json
import os
import re
import subprocess
import urllib.parse
import urllib.request
from email.header import decode_header, make_header
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import parseaddr
from typing import List, Optional

from mrag.adapters.tool_groups import CompositeToolGroup, Tool, ToolGroup, ToolGroupRegistry

_MAX_HANDLER_CHARS = 8000  # raw ceiling before the runner's own truncation


def _clip(text: str) -> str:
    text = (text or "").strip()
    if len(text) > _MAX_HANDLER_CHARS:
        return text[:_MAX_HANDLER_CHARS] + "\n[...output clipped...]"
    return text


def _env(*names: str) -> Optional[str]:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return None


# ---------------------------------------------------------------------------
# email (composite: read + write subgroups behind a sub-orchestrator)
# ---------------------------------------------------------------------------

def _email_config():
    address = _env("MRAG_EMAIL_ADDRESS", "GMAIL_ADDRESS")
    password = _env("MRAG_EMAIL_PASSWORD", "GMAIL_APP_PASSWORD")
    if not address or not password:
        return None
    return {
        "address": address,
        "password": password,
        "imap_host": _env("MRAG_IMAP_HOST") or "imap.gmail.com",
        "smtp_host": _env("MRAG_SMTP_HOST") or "smtp.gmail.com",
    }


_EMAIL_CONFIG_ERROR = ("CONFIG ERROR: email is not configured — set "
                       "MRAG_EMAIL_ADDRESS and MRAG_EMAIL_PASSWORD (an app "
                       "password), and optionally MRAG_IMAP_HOST/MRAG_SMTP_HOST.")


def _imap_connect(config):
    import imaplib
    conn = imaplib.IMAP4_SSL(config["imap_host"])
    conn.login(config["address"], config["password"])
    conn.select("INBOX")
    return conn


def _decode(value) -> str:
    try:
        return str(make_header(decode_header(value or "")))
    except Exception:
        return str(value or "")


def _fetch_message(conn, email_id: str):
    status, data = conn.uid("fetch", email_id, "(RFC822)")
    if status != "OK" or not data or data[0] is None:
        return None
    return BytesParser().parsebytes(data[0][1])


def _message_text(message) -> str:
    if message.is_multipart():
        for part in message.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    return payload.decode(part.get_content_charset() or "utf-8", "replace")
        return "(no text/plain part)"
    payload = message.get_payload(decode=True)
    if payload:
        return payload.decode(message.get_content_charset() or "utf-8", "replace")
    return str(message.get_payload())


def search_inbox(query: str = "", limit: int = 5) -> str:
    """Recent inbox messages, newest first, optionally filtered."""
    config = _email_config()
    if not config:
        return _EMAIL_CONFIG_ERROR
    conn = _imap_connect(config)
    try:
        criteria = f'(TEXT "{query}")' if query else "ALL"
        status, data = conn.uid("search", None, criteria)
        if status != "OK":
            return f"ERROR: inbox search failed: {status}"
        uids = data[0].split()
        if not uids:
            return "No matching emails."
        lines = []
        for uid in reversed(uids[-int(limit):]):
            status, header_data = conn.uid(
                "fetch", uid, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
            if status != "OK" or not header_data or header_data[0] is None:
                continue
            headers = BytesParser().parsebytes(header_data[0][1])
            lines.append(
                f"id={uid.decode()} | from: {_decode(headers.get('From'))} | "
                f"date: {_decode(headers.get('Date'))} | subject: {_decode(headers.get('Subject'))}")
        return _clip("\n".join(lines) or "No matching emails.")
    finally:
        conn.logout()


def read_email(email_id: str) -> str:
    """Full body of one email by the id search_inbox returned."""
    config = _email_config()
    if not config:
        return _EMAIL_CONFIG_ERROR
    conn = _imap_connect(config)
    try:
        message = _fetch_message(conn, str(email_id))
        if message is None:
            return f"ERROR: no email with id {email_id}."
        return _clip(
            f"From: {_decode(message.get('From'))}\n"
            f"Date: {_decode(message.get('Date'))}\n"
            f"Subject: {_decode(message.get('Subject'))}\n\n"
            f"{_message_text(message)}")
    finally:
        conn.logout()


def mark_read(email_id: str) -> str:
    config = _email_config()
    if not config:
        return _EMAIL_CONFIG_ERROR
    conn = _imap_connect(config)
    try:
        conn.uid("store", str(email_id), "+FLAGS", "(\\Seen)")
        return f"ok, marked {email_id} read"
    finally:
        conn.logout()


def _smtp_send(config, message: EmailMessage):
    import smtplib
    with smtplib.SMTP_SSL(config["smtp_host"], 465) as smtp:
        smtp.login(config["address"], config["password"])
        smtp.send_message(message)


def send_email(to: str, subject: str, body: str) -> str:
    config = _email_config()
    if not config:
        return _EMAIL_CONFIG_ERROR
    message = EmailMessage()
    message["From"] = config["address"]
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)
    _smtp_send(config, message)
    return f"ok, sent to {to}"


def reply_email(email_id: str, body: str) -> str:
    """Reply to an email by id, threading headers included."""
    config = _email_config()
    if not config:
        return _EMAIL_CONFIG_ERROR
    conn = _imap_connect(config)
    try:
        original = _fetch_message(conn, str(email_id))
    finally:
        conn.logout()
    if original is None:
        return f"ERROR: no email with id {email_id}."
    reply = EmailMessage()
    reply["From"] = config["address"]
    reply["To"] = parseaddr(original.get("Reply-To") or original.get("From"))[1]
    subject = _decode(original.get("Subject"))
    reply["Subject"] = subject if subject.lower().startswith("re:") else f"Re: {subject}"
    message_id = original.get("Message-ID")
    if message_id:
        reply["In-Reply-To"] = message_id
        reply["References"] = f"{original.get('References', '')} {message_id}".strip()
    reply.set_content(body)
    _smtp_send(config, reply)
    return f"ok, replied to {reply['To']}"


def build_email_group() -> CompositeToolGroup:
    """Email as a composite: 5 tools split into read/write subgroups, each
    a 1-5 tool subagent under the email sub-orchestrator."""
    registry = ToolGroupRegistry()
    registry.register(ToolGroup(
        name="email_read",
        summary="search the inbox, read messages, mark them read",
        tools=[
            Tool("search_inbox", "List recent inbox emails (newest first), optionally filtered by text.",
                 handler=search_inbox,
                 parameters={"query": "string, optional filter text", "limit": "int, default 5"}),
            Tool("read_email", "Read one email's full body by id.",
                 handler=read_email, parameters={"email_id": "string, id from search_inbox"}),
            Tool("mark_read", "Mark an email read.",
                 handler=mark_read, parameters={"email_id": "string"},
                 informational=False),
        ],
    ))
    registry.register(ToolGroup(
        name="email_write",
        summary="send new emails and reply to existing ones",
        tools=[
            Tool("send_email", "Send a new email.",
                 handler=send_email,
                 parameters={"to": "string, recipient address", "subject": "string", "body": "string"},
                 informational=False),
            Tool("reply_email", "Reply to an email by id (threads correctly).",
                 handler=reply_email,
                 parameters={"email_id": "string, id from search_inbox", "body": "string"},
                 informational=False),
        ],
    ))
    return CompositeToolGroup(
        name="email",
        summary="full email interface: search/read the inbox, send and reply",
        registry=registry,
    )


# ---------------------------------------------------------------------------
# telegram / discord comms
# ---------------------------------------------------------------------------

def telegram_send(text: str, chat_id: str = "") -> str:
    token = _env("TELEGRAM_BOT_TOKEN", "HELIX_TELEGRAM_TOKEN")
    chat = chat_id or _env("TELEGRAM_CHAT_ID", "TELEGRAM_OWNER_ID")
    if not token or not chat:
        return ("CONFIG ERROR: set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID "
                "(or HELIX_TELEGRAM_TOKEN / TELEGRAM_OWNER_ID).")
    payload = json.dumps({"chat_id": chat, "text": text}).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as response:
        result = json.loads(response.read().decode("utf-8"))
    return "ok, sent" if result.get("ok") else f"ERROR: telegram: {result}"


def telegram_updates(limit: int = 5) -> str:
    """Recent messages sent to the bot."""
    token = _env("TELEGRAM_BOT_TOKEN", "HELIX_TELEGRAM_TOKEN")
    if not token:
        return "CONFIG ERROR: set TELEGRAM_BOT_TOKEN (or HELIX_TELEGRAM_TOKEN)."
    with urllib.request.urlopen(
            f"https://api.telegram.org/bot{token}/getUpdates?limit={int(limit)}",
            timeout=60) as response:
        result = json.loads(response.read().decode("utf-8"))
    if not result.get("ok"):
        return f"ERROR: telegram: {result}"
    lines = []
    for update in result.get("result", [])[-int(limit):]:
        message = update.get("message") or update.get("edited_message") or {}
        sender = (message.get("from") or {}).get("first_name", "?")
        lines.append(f"{sender}: {message.get('text', '(non-text message)')}")
    return _clip("\n".join(lines) or "No recent messages.")


def discord_send(text: str) -> str:
    webhook = _env("DISCORD_WEBHOOK_URL")
    if not webhook:
        return "CONFIG ERROR: set DISCORD_WEBHOOK_URL (a channel webhook)."
    payload = json.dumps({"content": text}).encode("utf-8")
    req = urllib.request.Request(
        webhook, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as response:
        response.read()
    return "ok, sent"


def build_telegram_group() -> ToolGroup:
    return ToolGroup(
        name="telegram",
        summary="send Telegram messages and read recent ones sent to the bot",
        tools=[
            Tool("telegram_send", "Send a Telegram message (default chat unless chat_id given).",
                 handler=telegram_send,
                 parameters={"text": "string", "chat_id": "string, optional"},
                 informational=False),
            Tool("telegram_updates", "Read recent messages sent to the bot.",
                 handler=telegram_updates, parameters={"limit": "int, default 5"}),
        ],
    )


def build_discord_group() -> ToolGroup:
    return ToolGroup(
        name="discord",
        summary="post messages to a Discord channel",
        tools=[
            Tool("discord_send", "Post a message to the configured Discord channel webhook.",
                 handler=discord_send, parameters={"text": "string"},
                 informational=False),
        ],
    )


# ---------------------------------------------------------------------------
# web
# ---------------------------------------------------------------------------

_TAG_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.DOTALL | re.IGNORECASE)
_HTML_RE = re.compile(r"<[^>]+>")


def _html_to_text(html: str) -> str:
    text = _TAG_RE.sub(" ", html)
    text = _HTML_RE.sub(" ", text)
    text = html_lib.unescape(text)
    return re.sub(r"[ \t]*\n[ \t\n]*", "\n", re.sub(r"[ \t]+", " ", text)).strip()


def web_search(query: str, count: int = 5) -> str:
    """Brave Search API when BRAVE_API_KEY is set; DuckDuckGo HTML otherwise."""
    brave_key = _env("BRAVE_API_KEY")
    if brave_key:
        url = ("https://api.search.brave.com/res/v1/web/search?"
               + urllib.parse.urlencode({"q": query, "count": int(count)}))
        req = urllib.request.Request(url, headers={
            "X-Subscription-Token": brave_key, "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as response:
            data = json.loads(response.read().decode("utf-8"))
        results = (data.get("web") or {}).get("results", [])[: int(count)]
        lines = [f"{r.get('title')}\n  {r.get('url')}\n  {_html_to_text(r.get('description', ''))}"
                 for r in results]
        return _clip("\n".join(lines) or "No results.")

    url = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q": query})
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (mRAG starter)"})
    with urllib.request.urlopen(req, timeout=60) as response:
        page = response.read().decode("utf-8", "replace")
    hits = re.findall(
        r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', page)[: int(count)]
    lines = [f"{_html_to_text(title)}\n  {href}" for href, title in hits]
    return _clip("\n".join(lines) or "No results.")


def read_url(url: str) -> str:
    """Fetch a page and return its text content."""
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (mRAG starter)"})
    with urllib.request.urlopen(req, timeout=120) as response:
        raw = response.read(2_000_000)
    return _clip(_html_to_text(raw.decode("utf-8", "replace")))


def build_web_group() -> ToolGroup:
    return ToolGroup(
        name="web",
        summary="search the web and read pages",
        tools=[
            Tool("web_search", "Search the web; returns title, url, snippet per result.",
                 handler=web_search,
                 parameters={"query": "string", "count": "int, default 5"}),
            Tool("read_url", "Fetch a URL and return its readable text.",
                 handler=read_url, parameters={"url": "string, full http(s) URL"}),
        ],
    )


# ---------------------------------------------------------------------------
# files
# ---------------------------------------------------------------------------

def _files_root() -> str:
    return os.path.abspath(_env("MRAG_FILES_ROOT") or os.getcwd())


def _safe_path(path: str) -> Optional[str]:
    root = _files_root()
    resolved = os.path.abspath(os.path.join(root, path))
    if resolved != root and not resolved.startswith(root + os.sep):
        return None
    return resolved


def read_file(path: str) -> str:
    resolved = _safe_path(path)
    if not resolved:
        return f"ERROR: path escapes the files root ({_files_root()})."
    if not os.path.isfile(resolved):
        return f"ERROR: no file at {path}."
    with open(resolved, "r", errors="replace") as f:
        content = f.read()
    if not content.strip():
        # An unambiguous raw fact: a bare empty string invites the
        # reporting subagent to hallucinate contents for its summary.
        return f"(the file {path} exists but is EMPTY — 0 bytes of content)"
    return _clip(content)


def write_file(path: str, text: str) -> str:
    resolved = _safe_path(path)
    if not resolved:
        return f"ERROR: path escapes the files root ({_files_root()})."
    if not (text or "").strip():
        # Empty content is virtually always an upstream extraction
        # failure (truncated/malformed tool args), not intent — writing
        # a 0-byte file would report as success and mask the loss.
        return ("ERROR: refusing to write empty content to "
                f"{path} — the text argument arrived empty.")
    os.makedirs(os.path.dirname(resolved) or ".", exist_ok=True)
    with open(resolved, "w") as f:
        f.write(text)
    return f"ok, wrote {len(text)} chars to {path}"


def append_file(path: str, text: str) -> str:
    resolved = _safe_path(path)
    if not resolved:
        return f"ERROR: path escapes the files root ({_files_root()})."
    with open(resolved, "a") as f:
        f.write(text)
    return f"ok, appended {len(text)} chars to {path}"


def list_dir(path: str = ".") -> str:
    resolved = _safe_path(path)
    if not resolved:
        return f"ERROR: path escapes the files root ({_files_root()})."
    if not os.path.isdir(resolved):
        return f"ERROR: no directory at {path}."
    entries = sorted(os.listdir(resolved))
    return _clip("\n".join(
        f"{name}/" if os.path.isdir(os.path.join(resolved, name)) else name
        for name in entries) or "(empty)")


def search_files(text: str, path: str = ".") -> str:
    """Case-insensitive text search across files under a directory."""
    resolved = _safe_path(path)
    if not resolved:
        return f"ERROR: path escapes the files root ({_files_root()})."
    needle = text.lower()
    matches: List[str] = []
    for root, dirs, files in os.walk(resolved):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("venv", "node_modules", "__pycache__")]
        for name in files:
            full = os.path.join(root, name)
            try:
                with open(full, "r", errors="replace") as f:
                    for line_number, line in enumerate(f, 1):
                        if needle in line.lower():
                            rel = os.path.relpath(full, _files_root())
                            matches.append(f"{rel}:{line_number}: {line.strip()[:160]}")
                            break
            except OSError:
                continue
            if len(matches) >= 20:
                return _clip("\n".join(matches) + "\n[...more matches exist...]")
    return _clip("\n".join(matches) or "No matches.")


def build_files_group() -> ToolGroup:
    return ToolGroup(
        name="files",
        summary="read, write, list, and search files under the configured root",
        tools=[
            Tool("read_file", "Read a file.", handler=read_file,
                 parameters={"path": "string, relative to the files root"}),
            Tool("write_file", "Write (overwrite) a file.", handler=write_file,
                 parameters={"path": "string", "text": "string"}, informational=False),
            Tool("append_file", "Append to a file.", handler=append_file,
                 parameters={"path": "string", "text": "string"}, informational=False),
            Tool("list_dir", "List a directory.", handler=list_dir,
                 parameters={"path": "string, default '.'"}),
            Tool("search_files", "Find files containing text (first match per file).",
                 handler=search_files,
                 parameters={"text": "string to find", "path": "string, default '.'"}),
        ],
    )


# ---------------------------------------------------------------------------
# notes
# ---------------------------------------------------------------------------

def _notes_path() -> str:
    return _env("MRAG_NOTES_PATH") or os.path.expanduser("~/.mrag_notes.json")


def _load_notes() -> List[dict]:
    try:
        with open(_notes_path()) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return []


def _save_notes(notes: List[dict]):
    with open(_notes_path(), "w") as f:
        json.dump(notes, f, indent=1)


def save_note(text: str) -> str:
    notes = _load_notes()
    notes.append({"text": text, "done": False})
    _save_notes(notes)
    return f"ok, saved note #{len(notes)}"


def list_notes() -> str:
    notes = _load_notes()
    if not notes:
        return "No notes."
    return _clip("\n".join(
        f"#{index + 1} [{'x' if note.get('done') else ' '}] {note.get('text')}"
        for index, note in enumerate(notes)))


def complete_note(number: int) -> str:
    notes = _load_notes()
    index = int(number) - 1
    if index < 0 or index >= len(notes):
        return f"ERROR: no note #{number}."
    notes[index]["done"] = True
    _save_notes(notes)
    return f"ok, completed note #{number}"


def build_notes_group() -> ToolGroup:
    return ToolGroup(
        name="notes",
        summary="save, list, and complete the user's notes/todos",
        tools=[
            Tool("save_note", "Save a note/todo.", handler=save_note,
                 parameters={"text": "string"}, informational=False),
            Tool("list_notes", "List all notes with numbers and done-state.",
                 handler=list_notes, parameters={}),
            Tool("complete_note", "Mark a note done by number.", handler=complete_note,
                 parameters={"number": "int, from list_notes"}, informational=False),
        ],
    )


# ---------------------------------------------------------------------------
# shell (opt-in)
# ---------------------------------------------------------------------------

def run_command(command: str) -> str:
    """Run a shell command in the files root; stdout+stderr, clipped."""
    try:
        from core.security import shell_tools_enabled
        if not shell_tools_enabled():
            return "SECURITY POLICY: shell commands are disabled."
    except ImportError:
        return "SECURITY POLICY: shell policy is unavailable."
    result = subprocess.run(
        command, shell=True, cwd=_files_root(),
        capture_output=True, text=True)
    output = (result.stdout or "") + (result.stderr or "")
    status = "" if result.returncode == 0 else f"\n[exit code {result.returncode}]"
    return _clip(output + status) or f"(no output){status}"


def build_shell_group() -> ToolGroup:
    return ToolGroup(
        name="shell",
        summary="run shell commands in the files root",
        tools=[
            Tool("run_command", "Run a shell command; returns stdout+stderr.",
                 handler=run_command, parameters={"command": "string"}),
        ],
    )


def build_workspace_group() -> ToolGroup:
    """Coding/troubleshooting workspace: ONE subagent that can explore,
    edit, and run — the read-fix-verify loop needs all three in a single
    context, and splitting them across files/shell groups forces the loop
    back through the planner one micro-step at a time. Exactly 5 tools.
    Opt-in like shell (it embeds run_command)."""
    return ToolGroup(
        name="workspace",
        summary=("troubleshoot and edit a project: read/write/search files "
                 "AND run commands to verify, all in one place"),
        tools=[
            Tool("list_dir", "List a directory.", handler=list_dir,
                 parameters={"path": "string, default '.'"}),
            Tool("read_file", "Read a file.", handler=read_file,
                 parameters={"path": "string, relative to the files root"}),
            Tool("write_file", "Write (overwrite) a file.", handler=write_file,
                 parameters={"path": "string", "text": "string"}, informational=False),
            Tool("search_files", "Find files containing text (first match per file).",
                 handler=search_files,
                 parameters={"text": "string to find", "path": "string, default '.'"}),
            Tool("run_command", "Run a shell command in the files root; returns stdout+stderr.",
                 handler=run_command, parameters={"command": "string"}),
        ],
    )


# ---------------------------------------------------------------------------
# assembly
# ---------------------------------------------------------------------------

def build_starter_registry(include_shell: bool = False,
                           registry: Optional[ToolGroupRegistry] = None) -> ToolGroupRegistry:
    """The full starter suite as one registry, ready for ToolOrchestrator.
    Shell is opt-in: it executes arbitrary commands, so wiring it is an
    explicit decision, not a default."""
    from mrag.adapters.scheduler import build_schedule_group

    registry = registry or ToolGroupRegistry()
    registry.register(build_email_group())
    registry.register(build_telegram_group())
    registry.register(build_discord_group())
    registry.register(build_web_group())
    registry.register(build_files_group())
    registry.register(build_notes_group())
    registry.register(build_schedule_group())
    if include_shell:
        registry.register(build_shell_group())
    return registry

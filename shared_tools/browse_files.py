"""Universal local-PC file research tool, shared by every AIMAOS agent.

Lets an agent explore directories, search by name/content, and read files
anywhere under ~ — the raw material for reasoning out a plan.
Reads are size-capped; the ToolSubagent layer chunk-summarizes anything big.
"""
import os
import re

ALLOWED_ROOT = os.path.expanduser("~")
MAX_READ_CHARS = 12000
MAX_LIST_ENTRIES = 60
MAX_SEARCH_HITS = 20

# Paths under ALLOWED_ROOT that are known stale/orphaned, not live office
# data -- e.g. ~/.agent_company is leftover from before this project
# was restructured into AIMAOS and isn't referenced anywhere in current code,
# but it's still "under ~" so agents have wandered into it and
# reported its day-old, unrelated contents (like an old office_board.json)
# as if it were the live system. Denied explicitly rather than narrowing
# ALLOWED_ROOT itself, since agents legitimately need to reach real client
# files dropped anywhere under the home directory (e.g. ~/Downloads).
DENIED_PATHS = (os.path.expanduser("~/.agent_company"),)

TOOL_DEFINITION = {
    "name": "browse_files",
    "description": "Explores the local computer: list a directory, search files by name or content, "
                   "or read a file's text. Paths must be under ~.",
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["list", "search", "read"],
                "description": "list: directory contents; search: find files by name/content; read: file text."
            },
            "path": {
                "type": "string",
                "description": "Absolute directory path (list/search) or file path (read)."
            },
            "query": {
                "type": "string",
                "description": "search only: text to find in filenames or file contents."
            }
        },
        "required": ["action", "path"]
    }
}


def _safe(path):
    real = os.path.realpath(path)
    if not real.startswith(ALLOWED_ROOT):
        raise ValueError(f"Path {path} is outside the allowed root {ALLOWED_ROOT}")
    for denied in DENIED_PATHS:
        if real == denied or real.startswith(denied + os.sep):
            raise ValueError(f"Path {path} is a known stale/unrelated directory, not live office data.")
    return real


def _read_text(path, limit=MAX_READ_CHARS):
    if path.lower().endswith(".docx"):
        try:
            import docx
            d = docx.Document(path)
            return "\n".join(p.text for p in d.paragraphs)[:limit]
        except Exception as e:
            return f"(could not extract docx text: {e})"
    if path.lower().endswith(".pdf"):
        try:
            from pypdf import PdfReader
            return "\n".join((pg.extract_text() or "") for pg in PdfReader(path).pages)[:limit]
        except Exception as e:
            return f"(could not extract pdf text: {e})"
    try:
        with open(path, "r", errors="replace") as f:
            return f.read(limit)
    except Exception as e:
        return f"(could not read file: {e})"


def execute(action, path, query=None):
    path = _safe(path)

    if action == "list":
        if not os.path.isdir(path):
            return f"Not a directory: {path}"
        entries = sorted(os.listdir(path))
        hidden = len(entries) - MAX_LIST_ENTRIES
        lines = []
        for e in entries[:MAX_LIST_ENTRIES]:
            full = os.path.join(path, e)
            kind = "DIR " if os.path.isdir(full) else "FILE"
            size = "" if os.path.isdir(full) else f" ({os.path.getsize(full)} bytes)"
            lines.append(f"[{kind}] {e}{size}")
        out = f"Contents of {path} ({len(entries)} entries):\n" + "\n".join(lines)
        if hidden > 0:
            out += f"\n... and {hidden} more entries"
        return out

    if action == "search":
        if not query:
            return "search requires a query."
        if not os.path.isdir(path):
            return f"Not a directory: {path}"
        q = query.lower()
        hits = []
        for root, dirs, files in os.walk(path):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__" and d != ".venv"]
            for fname in files:
                full = os.path.join(root, fname)
                if q in fname.lower():
                    hits.append(f"{full} (filename match)")
                elif os.path.getsize(full) < 400_000 and not fname.lower().endswith(
                        (".docx", ".pdf", ".zip", ".png", ".jpg", ".gguf", ".bin")):
                    try:
                        with open(full, "r", errors="replace") as f:
                            content = f.read(200_000)
                        idx = content.lower().find(q)
                        if idx >= 0:
                            snippet = content[max(0, idx - 60):idx + 90].replace("\n", " ")
                            hits.append(f"{full} (content match: ...{snippet}...)")
                    except Exception:
                        pass
                if len(hits) >= MAX_SEARCH_HITS:
                    break
            if len(hits) >= MAX_SEARCH_HITS:
                break
        if not hits:
            return f"No matches for '{query}' under {path}."
        return f"Matches for '{query}' under {path}:\n" + "\n".join(hits)

    if action == "read":
        if not os.path.isfile(path):
            return f"Not a file: {path}"
        text = _read_text(path)
        truncated = " (truncated)" if len(text) >= MAX_READ_CHARS else ""
        return f"Content of {path}{truncated}:\n{text}"

    return f"Unknown action '{action}'. Use list, search, or read."

"""Fetches a single web page and returns its readable text, shared by every
AIMAOS agent. Pairs with web_search.py: search to find a URL, fetch to read
it. Pure `requests` + stdlib — no headless browser, so JS-rendered pages will
come back thin (fetch the API/JSON endpoint directly in that case).
"""
import re
import html as html_lib

import requests

USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AIMAOS-OfficeAgent/1.0"
REQUEST_TIMEOUT = 15
MAX_DOWNLOAD_BYTES = 3_000_000
DEFAULT_MAX_CHARS = 6000

TOOL_DEFINITION = {
    "name": "web_fetch",
    "description": "Fetches a web page by URL and returns its readable text content with HTML stripped "
                   "out. Use after web_search to read a specific result in full.",
    "parameters": {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "Full URL to fetch, including http:// or https://."
            },
            "max_chars": {
                "type": "integer",
                "description": f"Maximum characters of extracted text to return (default {DEFAULT_MAX_CHARS})."
            }
        },
        "required": ["url"]
    }
}

_SCRIPT_STYLE_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.DOTALL | re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.DOTALL | re.IGNORECASE)
_WHITESPACE_RE = re.compile(r"[ \t]+")
_BLANKLINES_RE = re.compile(r"\n{3,}")


def _html_to_text(raw_html):
    no_script = _SCRIPT_STYLE_RE.sub(" ", raw_html)
    text = _TAG_RE.sub("\n", no_script)
    text = html_lib.unescape(text)
    text = _WHITESPACE_RE.sub(" ", text)
    text = _BLANKLINES_RE.sub("\n\n", text)
    return text.strip()


def execute(url, max_chars=DEFAULT_MAX_CHARS):
    if not url or not url.lower().startswith(("http://", "https://")):
        return "Error: url must start with http:// or https://."
    max_chars = int(max_chars or DEFAULT_MAX_CHARS)

    try:
        resp = requests.get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT,
            stream=True,
        )
        resp.raise_for_status()
        content_type = resp.headers.get("Content-Type", "")
        chunks, size = [], 0
        for chunk in resp.iter_content(chunk_size=65536):
            chunks.append(chunk)
            size += len(chunk)
            if size >= MAX_DOWNLOAD_BYTES:
                break
        body = b"".join(chunks).decode(resp.encoding or "utf-8", errors="replace")
    except requests.exceptions.RequestException as e:
        return f"Fetch failed for {url}: {e}"

    if "html" not in content_type and "text" not in content_type:
        return f"Fetched {url} (Content-Type: {content_type or 'unknown'}) — not text/HTML, cannot extract readable text."

    title_match = _TITLE_RE.search(body)
    title = html_lib.unescape(_TAG_RE.sub("", title_match.group(1))).strip() if title_match else "(no title)"
    text = _html_to_text(body)
    truncated = len(text) > max_chars
    text = text[:max_chars]

    header = f"Title: {title}\nURL: {url}\n\n"
    footer = "\n\n[truncated]" if truncated else ""
    return header + text + footer

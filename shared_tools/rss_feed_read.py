"""RSS/Atom feed reader, shared by every AIMAOS agent. No API key needed —
useful for Quinn watching legal-news feeds or Marley watching court-calendar
feeds. Pure stdlib XML parsing + requests.
"""
import xml.etree.ElementTree as ET

import requests

REQUEST_TIMEOUT = 15
MAX_ITEMS_CAP = 20
_ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}

TOOL_DEFINITION = {
    "name": "rss_feed_read",
    "description": "Fetches an RSS or Atom feed URL and returns the latest item titles, links, and dates.",
    "parameters": {
        "type": "object",
        "properties": {
            "feed_url": {
                "type": "string",
                "description": "URL of the RSS or Atom feed."
            },
            "max_items": {
                "type": "integer",
                "description": f"How many items to return (1-{MAX_ITEMS_CAP}, default 10)."
            }
        },
        "required": ["feed_url"]
    }
}


def _parse_rss(root, max_items):
    items = root.findall(".//item")[:max_items]
    lines = []
    for it in items:
        title = (it.findtext("title") or "(untitled)").strip()
        link = (it.findtext("link") or "").strip()
        date = (it.findtext("pubDate") or "").strip()
        lines.append(f"- {title} ({date})\n  {link}")
    return lines


def _parse_atom(root, max_items):
    entries = root.findall("atom:entry", _ATOM_NS)[:max_items]
    lines = []
    for e in entries:
        title = (e.findtext("atom:title", namespaces=_ATOM_NS) or "(untitled)").strip()
        link_el = e.find("atom:link", _ATOM_NS)
        link = link_el.get("href") if link_el is not None else ""
        date = (e.findtext("atom:updated", namespaces=_ATOM_NS) or "").strip()
        lines.append(f"- {title} ({date})\n  {link}")
    return lines


def execute(feed_url, max_items=10):
    if not feed_url or not feed_url.lower().startswith(("http://", "https://")):
        return "Error: feed_url must start with http:// or https://."
    max_items = max(1, min(int(max_items or 10), MAX_ITEMS_CAP))

    try:
        resp = requests.get(feed_url, timeout=REQUEST_TIMEOUT,
                            headers={"User-Agent": "AIMAOS-OfficeAgent/1.0"})
        resp.raise_for_status()
    except requests.exceptions.RequestException as e:
        return f"Feed fetch failed: {e}"

    try:
        root = ET.fromstring(resp.content)
    except ET.ParseError as e:
        return f"Feed at {feed_url} is not valid XML: {e}"

    lines = _parse_rss(root, max_items)
    if not lines:
        lines = _parse_atom(root, max_items)
    if not lines:
        return f"No items found in feed {feed_url} (unrecognized RSS/Atom structure)."
    return f"{len(lines)} item(s) from {feed_url}:\n" + "\n".join(lines)

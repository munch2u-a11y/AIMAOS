"""Public web search, shared by every AIMAOS agent.

Tries providers in order of reliability:
  1. Brave Search API   (BRAVE_SEARCH_API_KEY set)      — recommended
  2. SerpApi             (SERPAPI_KEY set)                — recommended
  3. DuckDuckGo HTML scrape (no key)                      — best-effort only;
     DuckDuckGo actively anti-bot-gates automated traffic (rate-limit page or
     an image CAPTCHA), so this path can fail even when the query is fine.
     It's here so the tool works with zero setup, not as a reliable primary.

Get a free key at https://brave.com/search/api/ or https://serpapi.com/ and
set the env var to upgrade to reliable results — see shared_tools/README.md.
"""
import re
import html as html_lib
from urllib.parse import unquote, urlparse, parse_qs

import os
import requests

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
MAX_RESULTS_CAP = 10
REQUEST_TIMEOUT = 15

TOOL_DEFINITION = {
    "name": "web_search",
    "description": "Searches the public web and returns a ranked list of result titles, URLs, and "
                   "snippets for a query. Uses a configured search API if available, otherwise a "
                   "best-effort no-key fallback.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query."
            },
            "max_results": {
                "type": "integer",
                "description": f"How many results to return (1-{MAX_RESULTS_CAP}, default 5)."
            }
        },
        "required": ["query"]
    }
}


def _format_results(query, source, items):
    lines = [f"{i + 1}. {t} — {u}\n   {s}" for i, (t, u, s) in enumerate(items)]
    return f"Search results for '{query}' via {source}:\n" + "\n".join(lines)


def _search_brave(query, max_results):
    key = os.environ.get("BRAVE_SEARCH_API_KEY")
    if not key:
        return None
    try:
        resp = requests.get(
            "https://api.search.brave.com/res/v1/web/search",
            params={"q": query, "count": max_results},
            headers={"Accept": "application/json", "X-Subscription-Token": key},
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        return f"Brave Search request failed: {e}"
    results = (data.get("web") or {}).get("results", [])[:max_results]
    if not results:
        return f"Brave Search returned no results for '{query}'."
    items = [(r.get("title", "(untitled)"), r.get("url", ""), r.get("description", "")) for r in results]
    return _format_results(query, "Brave Search", items)


def _search_serpapi(query, max_results):
    key = os.environ.get("SERPAPI_KEY")
    if not key:
        return None
    try:
        resp = requests.get(
            "https://serpapi.com/search.json",
            params={"q": query, "engine": "google", "num": max_results, "api_key": key},
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        return f"SerpApi request failed: {e}"
    results = data.get("organic_results", [])[:max_results]
    if not results:
        return f"SerpApi returned no results for '{query}'."
    items = [(r.get("title", "(untitled)"), r.get("link", ""), r.get("snippet", "")) for r in results]
    return _format_results(query, "SerpApi", items)


_RESULT_RE = re.compile(
    r'class="result-link"[^>]*href="(?P<href>[^"]+)"[^>]*>(?P<title>.*?)</a>'
    r'.*?class="result-snippet"[^>]*>(?P<snippet>.*?)</td>',
    re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")


def _strip_tags(fragment):
    return html_lib.unescape(_TAG_RE.sub("", fragment)).strip()


def _resolve_href(href):
    if href.startswith("//"):
        href = "https:" + href
    parsed = urlparse(href)
    qs = parse_qs(parsed.query)
    if "uddg" in qs:
        return unquote(qs["uddg"][0])
    return href


def _search_ddg_scrape(query, max_results):
    try:
        resp = requests.get(
            "https://lite.duckduckgo.com/lite/",
            params={"q": query},
            headers={"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"},
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
    except requests.exceptions.RequestException as e:
        return f"Web search failed (network/HTTP error): {e}"

    if "anomaly-modal" in resp.text or "challenge-form" in resp.text:
        return ("DuckDuckGo's anti-bot challenge blocked this no-key search request (this happens "
               "intermittently for automated traffic). Configure BRAVE_SEARCH_API_KEY or SERPAPI_KEY "
               "for reliable results — see shared_tools/README.md.")

    matches = list(_RESULT_RE.finditer(resp.text))[:max_results]
    if not matches:
        return (f"No results parsed for '{query}'. Either there were genuinely no hits, or "
                "DuckDuckGo's page layout changed and the parser needs updating.")
    items = []
    for m in matches:
        title = _strip_tags(m.group("title")) or "(untitled)"
        snippet = _strip_tags(m.group("snippet"))
        url = _resolve_href(m.group("href"))
        items.append((title, url, snippet))
    return _format_results(query, "DuckDuckGo (no-key)", items)


def execute(query, max_results=5):
    if not query or not query.strip():
        return "Error: query must not be empty."
    max_results = max(1, min(int(max_results or 5), MAX_RESULTS_CAP))

    for provider in (_search_brave, _search_serpapi):
        result = provider(query, max_results)
        if result is not None:
            return result
    return _search_ddg_scrape(query, max_results)

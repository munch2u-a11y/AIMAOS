"""Browses the shared AIMAOS tool catalog (shared_tools/tool_catalog.yaml).

For Zoe (tool_engineering) and Rae (agent_making): before hand-authoring a
new tool subagent with design_tool_subagent, check here first — a small
local model does much better naming a catalog entry than inventing a JSON
schema from scratch. Returns compact one-line-per-tool listings, never the
whole catalog, so results stay small enough for a tiny local model's context.
Follow up with action='detail' on a specific tool, then hand it to
install_catalog_tool.py.
"""
import os

def _find_aimaos_root():
    p = os.path.dirname(os.path.abspath(__file__))
    while p != os.path.dirname(p) and not os.path.exists(os.path.join(p, "aimaos_config.yaml")):
        p = os.path.dirname(p)
    return p
AIMAOS_ROOT = os.environ.get("AIMAOS_ROOT") or _find_aimaos_root()
import json

import yaml

CATALOG_PATH = os.path.join(AIMAOS_ROOT, "shared_tools/tool_catalog.yaml")
MAX_SEARCH_HITS = 15

TOOL_DEFINITION = {
    "name": "list_tool_catalog",
    "description": "Browses the shared tool catalog: list categories, search tools by keyword/category/"
                   "status, or get the full schema for one tool by name.",
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["list_categories", "search", "detail"],
                "description": "list_categories: category overview; search: filtered tool listing; "
                               "detail: full entry for one tool."
            },
            "query": {
                "type": "string",
                "description": "search only: keyword to match against tool name/description."
            },
            "category": {
                "type": "string",
                "description": "search only: restrict to one category key (see list_categories)."
            },
            "status": {
                "type": "string",
                "enum": ["implemented", "scaffold"],
                "description": "search only: restrict to tools of this status."
            },
            "tool_name": {
                "type": "string",
                "description": "detail only: exact catalog tool name."
            }
        },
        "required": ["action"]
    }
}


def _load_catalog():
    if not os.path.exists(CATALOG_PATH):
        return {"categories": {}, "tools": []}
    with open(CATALOG_PATH, "r") as f:
        return yaml.safe_load(f) or {"categories": {}, "tools": []}


def execute(action, query=None, category=None, status=None, tool_name=None):
    catalog = _load_catalog()
    categories = catalog.get("categories", {})
    tools = catalog.get("tools", [])

    if action == "list_categories":
        counts = {}
        for t in tools:
            counts[t.get("category")] = counts.get(t.get("category"), 0) + 1
        lines = [f"- {key} ({cfg.get('label', key)}): {counts.get(key, 0)} tool(s)"
                for key, cfg in categories.items()]
        return f"{len(categories)} catalog categories:\n" + "\n".join(lines)

    if action == "search":
        hits = []
        q = (query or "").lower()
        for t in tools:
            if category and t.get("category") != category:
                continue
            if status and t.get("status") != status:
                continue
            if q and q not in t.get("name", "").lower() and q not in t.get("description", "").lower():
                continue
            hits.append(t)
        if not hits:
            return "No catalog tools matched that search."
        shown = hits[:MAX_SEARCH_HITS]
        lines = [f"- {t['name']} [{t['status']}] ({t['category']}): {t['description']}" for t in shown]
        header = f"{len(hits)} match(es)"
        if len(hits) > len(shown):
            header += f", showing first {len(shown)} (narrow the search for the rest)"
        return f"{header}:\n" + "\n".join(lines)

    if action == "detail":
        if not tool_name:
            return "Error: detail requires tool_name."
        match = next((t for t in tools if t.get("name") == tool_name), None)
        if not match:
            close = [t["name"] for t in tools if tool_name.lower() in t["name"].lower()]
            hint = f" Closest names: {', '.join(close[:5])}." if close else ""
            return f"No catalog tool named '{tool_name}'.{hint}"
        return json.dumps(match, indent=1)

    return f"Unknown action '{action}'. Use list_categories, search, or detail."

"""Installs a tool from the shared AIMAOS tool catalog onto a target office
agent — the low-effort counterpart to Zoe's design_tool_subagent.py.

Where design_tool_subagent asks the calling model to invent a full schema
and seed beliefs from nothing, this tool looks all of that up in
shared_tools/tool_catalog.yaml, so the calling model only has to name the
target agent and a catalog tool. For an "implemented" catalog entry it
registers the existing shared_tools module directly (same file, many
agents — the browse_files.py pattern); for a "scaffold" entry it generates
a stub module in the target's own tools/ dir, exactly like
design_tool_subagent's template, ready for a developer or Zoe to fill in
(or pass command_template to wrap a local shell command immediately).

Use shared_tools/list_tool_catalog.py first to find the right tool_name.
"""
import os

def _find_aimaos_root():
    p = os.path.dirname(os.path.abspath(__file__))
    while p != os.path.dirname(p) and not os.path.exists(os.path.join(p, "aimaos_config.yaml")):
        p = os.path.dirname(p)
    return p
AIMAOS_ROOT = os.environ.get("AIMAOS_ROOT") or _find_aimaos_root()
import json
from datetime import datetime

import yaml

CATALOG_PATH = os.path.join(AIMAOS_ROOT, "shared_tools", "tool_catalog.yaml")

TOOL_DEFINITION = {
    "name": "install_catalog_tool",
    "description": "Installs a tool from the shared tool catalog onto a target office agent: registers "
                   "an implemented shared module directly, or generates a scaffold module for one not "
                   "yet implemented. Registers the capability domain and seeds beliefs from the catalog.",
    "parameters": {
        "type": "object",
        "properties": {
            "target_agent": {
                "type": "string",
                "description": "Agent receiving the tool (e.g. 'Marley', 'Quinn', or a Rae-made clone)."
            },
            "tool_name": {
                "type": "string",
                "description": "Catalog tool name, from list_tool_catalog (e.g. 'google_calendar', 'web_search')."
            },
            "command_template": {
                "type": "string",
                "description": "Scaffold entries only: optional local shell command implementing the tool; "
                               "argument names in {braces} are filled from the call."
            }
        },
        "required": ["target_agent", "tool_name"]
    }
}

_MODULE_TEMPLATE = '''"""Tool subagent: {tool_name} (installed from the shared catalog for {target_agent}, {date})."""
import subprocess

TOOL_DEFINITION = {definition}

COMMAND_TEMPLATE = {command_template!r}


def execute(**kwargs):
    if COMMAND_TEMPLATE:
        try:
            cmd = COMMAND_TEMPLATE.format(**kwargs)
        except KeyError as e:
            return f"Missing argument for command template: {{e}}"
        try:
            proc = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=120)
            out = (proc.stdout or "") + (("\\n[stderr] " + proc.stderr) if proc.stderr.strip() else "")
            return out.strip() or f"(command exited {{proc.returncode}} with no output)"
        except Exception as e:
            return f"Command failed: {{e}}"
    return ("NOT YET IMPLEMENTED: installed from the shared catalog as a scaffold. Its schema and "
            "beliefs are registered; the implementation body in " + __file__ + " still needs to be written.")
'''


def _load_catalog():
    with open(CATALOG_PATH, "r") as f:
        return yaml.safe_load(f) or {}


def _register_domain_and_beliefs(caps_path, domain, domain_description, tool_path, seed_beliefs):
    caps = {}
    if os.path.exists(caps_path):
        try:
            with open(caps_path) as f:
                caps = yaml.safe_load(f) or {}
        except Exception:
            caps = {}
    domains = caps.setdefault("domains", {})
    dcfg = domains.setdefault(domain, {
        "description": domain_description or f"{domain.replace('_', ' ')} capability.",
        "tools": [],
    })
    rel = tool_path if not os.path.isabs(tool_path) else os.path.relpath(tool_path, AIMAOS_ROOT)
    if rel not in dcfg.setdefault("tools", []):
        dcfg["tools"].append(rel)

    seeds = caps.setdefault("seed_beliefs", [])
    for s in (seed_beliefs or []):
        if s not in seeds:
            seeds.append(s)

    with open(caps_path, "w") as f:
        yaml.dump(caps, f, sort_keys=False, width=110)


def execute(target_agent, tool_name, command_template=None):
    target_dir = os.path.join(AIMAOS_ROOT, f"{target_agent}-AI")
    if not os.path.isdir(target_dir):
        return f"Error: no agent workspace at {target_dir}. (Rae must clone the agent first.)"

    catalog = _load_catalog()
    entry = next((t for t in catalog.get("tools", []) if t.get("name") == tool_name), None)
    if entry is None:
        return (f"Error: no catalog tool named '{tool_name}'. Use list_tool_catalog to search "
                f"for the right name.")

    caps_path = os.path.join(target_dir, "capabilities.yaml")
    domain = entry.get("suggested_domain", "general")
    domain_description = entry.get("domain_description", "")
    seed_beliefs = entry.get("seed_beliefs", [])
    credentials_env = entry.get("credentials_env", [])

    if entry["status"] == "implemented":
        tool_path = entry["module"]
        if not os.path.isabs(tool_path):
            tool_path = os.path.join(AIMAOS_ROOT, tool_path)
        if not os.path.exists(tool_path):
            return f"Error: catalog says '{tool_name}' is implemented at {tool_path}, but that file is missing."
        _register_domain_and_beliefs(caps_path, domain, domain_description, tool_path, seed_beliefs)
        cred_note = (f" Needs env var(s) set to activate: {', '.join(credentials_env)}."
                    if credentials_env else " No credentials needed — works immediately.")
        return (f"Installed '{tool_name}' for {target_agent} from the shared catalog "
                f"(existing module: {tool_path}).\n"
                f"- Domain: '{domain}' in {caps_path}\n"
                f"- Seed beliefs added: {len(seed_beliefs)}\n"
                f"{cred_note}")

    # scaffold: generate a stub module in the target's own tools/ dir
    tools_dir = os.path.join(target_dir, "tools")
    os.makedirs(tools_dir, exist_ok=True)
    tool_path = os.path.join(tools_dir, f"{tool_name}.py")
    if os.path.exists(tool_path):
        return f"Error: {target_agent} already has a tool named {tool_name} ({tool_path})."

    definition = {
        "name": tool_name,
        "description": entry.get("description", tool_name),
        "parameters": {
            "type": "object",
            "properties": entry.get("parameters", {}),
            "required": entry.get("required", []),
        },
    }
    with open(tool_path, "w") as f:
        f.write(_MODULE_TEMPLATE.format(
            tool_name=tool_name, target_agent=target_agent,
            date=datetime.now().strftime("%Y-%m-%d"),
            definition=json.dumps(definition, indent=1),
            command_template=command_template or ""))

    _register_domain_and_beliefs(caps_path, domain, domain_description, tool_path, seed_beliefs)
    cred_note = (f" Once implemented it will need env var(s): {', '.join(credentials_env)}."
                if credentials_env else " Needs no credentials once implemented.")
    impl = "wraps local command" if command_template else "scaffold (implementation pending)"
    return (f"Installed '{tool_name}' for {target_agent} from the shared catalog as a new module.\n"
            f"- Module: {tool_path} ({impl})\n"
            f"- Domain: '{domain}' in {caps_path}\n"
            f"- Seed beliefs added: {len(seed_beliefs)}\n"
            f"{cred_note}")

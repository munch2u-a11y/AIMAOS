"""Zoe's tool-subagent factory.

Designs a new specialized tool subagent for any office agent: writes the tool
module (schema + executable body), registers it under a capability domain in
the target's capabilities.yaml, and seeds the target's first beliefs about
HOW the tool works. The ToolSubagent layer then builds the subagent's
minimalist system prompt from that schema + those beliefs at run time —
deliberately avoiding "You are the..." personas.
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
from datetime import datetime
from core.security import (
    SecurityValidationError,
    shell_tools_enabled,
    validate_agent_name,
    validate_tool_name,
)

TOOL_DEFINITION = {
    "name": "design_tool_subagent",
    "description": "Creates a new tool subagent for a target office agent: generates the tool module, "
                   "registers it under a capability domain, and seeds initial how-to-use beliefs. "
                   "Optionally wraps a local shell command as the tool's implementation.",
    "parameters": {
        "type": "object",
        "properties": {
            "target_agent": {
                "type": "string",
                "description": "Agent receiving the tool (e.g. 'Alix', 'Quinn', or a Rae-made clone like 'Sona')."
            },
            "tool_name": {
                "type": "string",
                "description": "snake_case tool name (e.g. 'comment_poster', 'notification_checker')."
            },
            "description": {
                "type": "string",
                "description": "One-sentence statement of what the tool does."
            },
            "parameters_schema": {
                "type": "object",
                "description": "JSON Schema 'properties' object for the tool's arguments "
                               "(e.g. {\"post_id\": {\"type\": \"string\"}, \"text\": {\"type\": \"string\"}})."
            },
            "required_params": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Which parameter names are required."
            },
            "domain": {
                "type": "string",
                "description": "Capability domain to register under (e.g. 'comment_interaction'). Created if new."
            },
            "domain_description": {
                "type": "string",
                "description": "Description for the domain if it does not exist yet."
            },
            "seed_beliefs": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Initial beliefs about HOW to use this tool well (2-3 short sentences)."
            },
            "command_template": {
                "type": "string",
                "description": "Optional local shell command implementing the tool; argument names in "
                               "{braces} are filled from the call (e.g. 'ls -la {path}'). Omit for a scaffold "
                               "whose body a developer (or Zoe) fills in later."
            }
        },
        "required": ["target_agent", "tool_name", "description", "parameters_schema", "domain"]
    }
}

_MODULE_TEMPLATE = '''"""Tool subagent: {tool_name} (designed by Zoe for {target_agent}, {date})."""
import shlex
import subprocess
from core.security import shell_tools_enabled

TOOL_DEFINITION = {definition}

COMMAND_TEMPLATE = {command_template!r}


def execute(**kwargs):
    if COMMAND_TEMPLATE:
        if not shell_tools_enabled():
            return "SECURITY POLICY: shell-backed tools are disabled."
        try:
            cmd = COMMAND_TEMPLATE.format(**kwargs)
        except KeyError as e:
            return f"Missing argument for command template: {{e}}"
        try:
            proc = subprocess.run(shlex.split(cmd), shell=False, capture_output=True, text=True, timeout=120)
            out = (proc.stdout or "") + (("\\n[stderr] " + proc.stderr) if proc.stderr.strip() else "")
            return out.strip() or f"(command exited {{proc.returncode}} with no output)"
        except Exception as e:
            return f"Command failed: {{e}}"
    return ("NOT YET IMPLEMENTED: this tool subagent is a scaffold. "
            "Its schema and beliefs are registered; the implementation body in "
            + __file__ + " still needs to be written.")
'''


def execute(target_agent, tool_name, description, parameters_schema,
            domain, required_params=None, domain_description=None,
            seed_beliefs=None, command_template=None):
    try:
        target_agent = validate_agent_name(target_agent)
        tool_name = validate_tool_name(tool_name)
        domain = validate_tool_name(domain, label="capability domain")
    except SecurityValidationError as exc:
        return f"Error: {exc}"
    if command_template and not shell_tools_enabled():
        return ("Error: shell-backed tool creation is disabled. Enable developer mode and "
                "security.allow_shell_tools only in an isolated development environment.")
    target_dir = os.path.join(AIMAOS_ROOT, f"{target_agent}-AI")
    if not os.path.isdir(target_dir):
        return f"Error: no agent workspace at {target_dir}. (Rae must clone the agent first.)"

    if isinstance(parameters_schema, str):
        try:
            parameters_schema = json.loads(parameters_schema)
        except Exception:
            return "Error: parameters_schema must be a JSON object of parameter properties."

    tools_dir = os.path.join(target_dir, "tools")
    os.makedirs(tools_dir, exist_ok=True)
    tool_path = os.path.join(tools_dir, f"{tool_name}.py")
    if os.path.exists(tool_path):
        return f"Error: {target_agent} already has a tool named {tool_name} ({tool_path})."

    definition = {
        "name": tool_name,
        "description": description,
        "parameters": {
            "type": "object",
            "properties": parameters_schema,
            "required": list(required_params or []),
        },
    }

    with open(tool_path, "w") as f:
        f.write(_MODULE_TEMPLATE.format(
            tool_name=tool_name, target_agent=target_agent,
            date=datetime.now().strftime("%Y-%m-%d"),
            definition=json.dumps(definition, indent=1),
            command_template=command_template or ""))

    # Register under the capability domain
    caps_path = os.path.join(target_dir, "capabilities.yaml")
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
    rel_tool_path = os.path.relpath(tool_path, AIMAOS_ROOT)
    if rel_tool_path not in dcfg.setdefault("tools", []):
        dcfg["tools"].append(rel_tool_path)

    # Seed the target's first how-to beliefs — the raw material the
    # ToolSubagent layer turns into this specialist's system prompt.
    seeds = caps.setdefault("seed_beliefs", [])
    for s in (seed_beliefs or []):
        if s not in seeds:
            seeds.append(s)

    with open(caps_path, "w") as f:
        yaml.dump(caps, f, sort_keys=False, width=110)

    impl = "wraps local command" if command_template else "scaffold (implementation pending)"
    return (f"Designed tool subagent '{tool_name}' for {target_agent}.\n"
            f"- Module: {tool_path} ({impl})\n"
            f"- Domain: '{domain}' in {caps_path}\n"
            f"- Seed beliefs added: {len(seed_beliefs or [])}\n"
            f"{target_agent} can use it on their next turn; their belief store "
            f"will grow from every use.")

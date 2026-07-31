import os

def _find_aimaos_root():
    p = os.path.dirname(os.path.abspath(__file__))
    while p != os.path.dirname(p) and not os.path.exists(os.path.join(p, "aimaos_config.yaml")):
        p = os.path.dirname(p)
    return p
AIMAOS_ROOT = os.environ.get("AIMAOS_ROOT") or _find_aimaos_root()
import sys
import yaml

sys.path.insert(0, os.path.join(AIMAOS_ROOT, "Alix-AI"))
from business.memory import DocumentProductionMemory

TOOL_DEFINITION = {
    "name": "manage_memory",
    "description": "Reads, saves, or manages persistent user preferences, document rules, template field mappings, and production audit logs across sessions.",
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["remember_preference", "remove_preference", "remember_mapping", "query_memory", "get_history"],
                "description": "The action to perform."
            },
            "rule_text": {
                "type": "string",
                "description": "The rule or preference instruction to remember or remove (e.g., 'Always use ALL CAPS for taxpayer names')."
            },
            "template_name": {
                "type": "string",
                "description": "Template name for mapping actions (e.g. 'tax_return_1040')."
            },
            "intake_field": {
                "type": "string",
                "description": "The raw intake field name (e.g., 'Taxpayer_SSN')."
            },
            "placeholder_field": {
                "type": "string",
                "description": "The template Jinja2 placeholder field (e.g., 'ssn')."
            }
        },
        "required": ["action"]
    }
}

def get_config():
    tools_dir = os.path.dirname(os.path.abspath(__file__))
    project_dir = os.path.dirname(tools_dir)
    config_path = os.path.join(project_dir, "config.yaml")
    if os.path.exists(config_path):
        with open(config_path, "r") as f:
            try:
                return yaml.safe_load(f)
            except Exception:
                pass
    return {}

def execute(action, rule_text=None, template_name=None, intake_field=None, placeholder_field=None):
    config = get_config()
    paths = config.get("paths", {})
    memory_dir = paths.get("memory", "./workspace/.memory")
    
    mem = DocumentProductionMemory(memory_dir=memory_dir)
    
    if action == "remember_preference":
        if not rule_text:
            return "Error: rule_text is required to remember a preference."
        added = mem.add_preference(rule_text)
        if added:
            return f"Success: Remembered new preference -> '{rule_text}'"
        return f"Note: Preference already exists -> '{rule_text}'"

    elif action == "remove_preference":
        if not rule_text:
            return "Error: rule_text is required to remove a preference."
        return mem.remove_preference(rule_text)

    elif action == "remember_mapping":
        if not template_name or not intake_field or not placeholder_field:
            return "Error: template_name, intake_field, and placeholder_field are required for remember_mapping."
        return mem.add_field_mapping(template_name, intake_field, placeholder_field)

    elif action == "query_memory":
        return mem.get_system_prompt_summary()

    elif action == "get_history":
        history = mem.get_production_history(limit=10)
        if not history:
            return "No document production history recorded yet."
        output = ["Document Production History (Last 10):"]
        for idx, item in enumerate(reversed(history), 1):
            ts = item.get("timestamp", "")[:19].replace("T", " ")
            output.append(
                f"{idx}. [{ts}] Template: '{item.get('template_used')}'\n"
                f"   Input: {item.get('input_file')}\n"
                f"   Output: {item.get('output_file')}\n"
                f"   Extracted Fields: {item.get('extracted_fields')}\n"
                f"   Status: {item.get('status')}"
            )
        return "\n".join(output)

    return f"Error: Unknown memory action '{action}'."

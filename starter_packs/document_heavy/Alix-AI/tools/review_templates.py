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
from business.subagents.template_reviewer import TemplateReviewer

TOOL_DEFINITION = {
    "name": "review_templates",
    "description": "Invokes the Template Reviewer subagent to audit, clean, and refine document templates in token-optimized paragraph chunks.",
    "parameters": {
        "type": "object",
        "properties": {
            "template_name": {
                "type": "string",
                "description": "Optional specific template to review (e.g. 'form_12_982_a' or 'will_template'). If omitted, all pending review notes are processed."
            },
            "note": {
                "type": "string",
                "description": "Optional specific revision note or request (e.g. 'Remove footer notes and ensure client_email field is mapped')."
            },
            "action": {
                "type": "string",
                "enum": ["process_pending", "review_single", "queue_note"],
                "description": "Action to perform: 'process_pending' (default), 'review_single', or 'queue_note'."
            }
        }
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

def execute(template_name=None, note=None, action="process_pending"):
    config = get_config()
    paths = config.get("paths", {})
    templates_dir = paths.get("templates", "./templates")
    memory_dir = paths.get("memory", "./workspace/.memory")

    reviewer = TemplateReviewer(templates_dir=templates_dir, memory_dir=memory_dir)

    if action == "queue_note" and template_name and note:
        res = reviewer.add_review_note(template_name, note)
        return res

    elif action == "review_single" or (template_name and not action == "queue_note"):
        if not template_name:
            return "Error: template_name is required for action 'review_single'."
        res = reviewer.review_and_refine_template(template_name, note=note)
        return f"Template Review Subagent Output:\n{res}"

    else:
        # Process pending notes
        res = reviewer.process_pending_notes()
        return f"Template Review Subagent Batch Output:\n{res}"

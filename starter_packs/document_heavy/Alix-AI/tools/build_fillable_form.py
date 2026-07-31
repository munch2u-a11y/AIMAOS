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
from business.document_engine import DocumentEngine
from core.security import SecurityValidationError, require_allowed_path, resolve_within, validate_slug

TOOL_DEFINITION = {
    "name": "build_fillable_form",
    "description": "Converts a template's underscore-line answer areas (a question followed by a bare "
                   "'____...' line) into real, empty Word content controls (form fields) plus document "
                   "protection, so a client's returned, filled-in answers can be read back deterministically "
                   "with read_filled_form instead of needing OCR or a vision model. This is a one-time "
                   "template-authoring step -- run it once per template, not per client -- and it's "
                   "idempotent (safe to re-run; already-converted fields are left alone).",
    "parameters": {
        "type": "object",
        "properties": {
            "template_name": {
                "type": "string",
                "description": "The template folder name (e.g. 'intake_name_change')."
            }
        },
        "required": ["template_name"]
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


def execute(template_name):
    config = get_config()
    project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    configured_templates = config.get("paths", {}).get("templates", "templates")
    if not os.path.isabs(configured_templates):
        configured_templates = os.path.join(project_dir, configured_templates)
    try:
        template_id = validate_slug(str(template_name), label="template identifier")
        templates_dir = require_allowed_path(configured_templates)
        docx_path = resolve_within(templates_dir, template_id, "template.docx", must_exist=True)
    except (SecurityValidationError, FileNotFoundError) as exc:
        return f"Error: {exc}"

    try:
        engine = DocumentEngine(docx_path)
        fields_created = engine.make_fillable(docx_path)
        engine.apply_forms_protection(docx_path)
    except Exception as e:
        return f"Error building fillable form for '{template_id}': {e}"

    if fields_created == 0:
        return (f"No underscore-line answer areas found in '{template_id}' (already converted, or this "
                f"template doesn't use that pattern) -- document protection was (re)applied at {docx_path}.")

    return (f"Success: converted {fields_created} answer area(s) in '{template_id}' into real fillable "
            f"form fields and applied document protection.\n- Template: {docx_path}\n"
            f"- Read a filled-in copy back with read_filled_form, not read_scanned_document.")

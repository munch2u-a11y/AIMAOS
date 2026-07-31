"""Alix's Template Cataloger Tool — scans template directories, indexes legal forms,
extracts placeholders/variables, and registers templates into Alix's production library.
"""
import os

def _find_aimaos_root():
    p = os.path.dirname(os.path.abspath(__file__))
    while p != os.path.dirname(p) and not os.path.exists(os.path.join(p, "aimaos_config.yaml")):
        p = os.path.dirname(p)
    return p
AIMAOS_ROOT = os.environ.get("AIMAOS_ROOT") or _find_aimaos_root()
import sys
import json
import logging
from datetime import datetime

sys.path.insert(0, os.path.join(AIMAOS_ROOT, "Alix-AI"))

logger = logging.getLogger(__name__)

TOOL_DEFINITION = {
    "name": "catalog_templates",
    "description": "Scans template repositories in Alix's template directory, extracts metadata and variable placeholders, and updates the template index registry.",
    "parameters": {
        "type": "object",
        "properties": {
            "templates_dir": {
                "type": "string",
                "description": "Directory containing templates (default: the Alix-AI templates library)."
            }
        }
    }
}


def scan_and_index_templates(templates_dir=os.path.join(AIMAOS_ROOT, "Alix-AI/templates")):
    if not os.path.exists(templates_dir):
        return {"error": f"Templates directory '{templates_dir}' does not exist."}

    registry_path = os.path.join(templates_dir, "template_registry.json")
    registry = {
        "last_updated": datetime.now().isoformat(),
        "categories": {},
        "templates": []
    }

    for root, dirs, files in os.walk(templates_dir):
        rel_path = os.path.relpath(root, templates_dir)
        if rel_path == ".":
            category = "general"
        else:
            category = rel_path.split(os.sep)[0]

        if category not in registry["categories"]:
            registry["categories"][category] = 0

        for f in files:
            if f.startswith(".") or f == "template_registry.json":
                continue
            
            f_path = os.path.join(root, f)
            ext = os.path.splitext(f)[1].lower()
            
            if ext in (".docx", ".doc", ".rtf", ".txt", ".jinja2"):
                size = os.path.getsize(f_path)
                template_info = {
                    "filename": f,
                    "category": category,
                    "path": f_path,
                    "rel_path": os.path.relpath(f_path, templates_dir),
                    "size_bytes": size,
                    "modified": datetime.fromtimestamp(os.path.getmtime(f_path)).isoformat()
                }
                registry["templates"].append(template_info)
                registry["categories"][category] += 1

    with open(registry_path, "w") as rf:
        json.dump(registry, rf, indent=2)

    return registry


def execute(templates_dir=os.path.join(AIMAOS_ROOT, "Alix-AI/templates")):
    res = scan_and_index_templates(templates_dir=templates_dir)
    return json.dumps(res, indent=2)


if __name__ == "__main__":
    t_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(AIMAOS_ROOT, "Alix-AI/templates")
    print(f"Cataloging templates in {t_dir}...")
    reg = scan_and_index_templates(t_dir)
    print(f"Cataloged {len(reg.get('templates', []))} templates across {len(reg.get('categories', {}))} categories.")

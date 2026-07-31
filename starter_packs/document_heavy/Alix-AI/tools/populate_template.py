import os

def _find_aimaos_root():
    p = os.path.dirname(os.path.abspath(__file__))
    while p != os.path.dirname(p) and not os.path.exists(os.path.join(p, "aimaos_config.yaml")):
        p = os.path.dirname(p)
    return p
AIMAOS_ROOT = os.environ.get("AIMAOS_ROOT") or _find_aimaos_root()
import sys
import yaml
from datetime import datetime

sys.path.insert(0, os.path.join(AIMAOS_ROOT, "Alix-AI"))
from business.document_engine import DocumentEngine
from core.security import normalize_slug, resolve_within, sanitize_output_basename

TOOL_DEFINITION = {
    "name": "populate_template",
    "description": "Populates a document template (.docx) with structured context fields, validates required variables, optionally inserts a Table of Contents (TOC), and renders output as .docx or .pdf.",
    "parameters": {
        "type": "object",
        "properties": {
            "template_name": {
                "type": "string",
                "description": "The name of the template folder or file (e.g., 'full_will_template' or 'trust_template')."
            },
            "context": {
                "type": "object",
                "description": "JSON object mapping template placeholder keys to values (e.g. {'client_name': 'Bob Smith', 'county': 'Volusia'})."
            },
            "output_name": {
                "type": "string",
                "description": "Optional output base filename (excluding extension)."
            },
            "output_format": {
                "type": "string",
                "enum": ["docx", "pdf"],
                "description": "Output format: 'docx' or 'pdf'."
            },
            "include_toc": {
                "type": "boolean",
                "description": "Whether to auto-generate a Word Table of Contents at the beginning of the document."
            }
        },
        "required": ["template_name", "context"]
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

def execute(template_name, context, output_name=None, output_format=None, include_toc=False):
    config = get_config()
    paths = config.get("paths", {})
    templates_dir = os.path.abspath(paths.get("templates", "./templates"))
    output_dir = os.path.abspath(paths.get("output", "./workspace/output"))

    # Normalize: models often pass "form_x.docx" when the template folder is
    # "form_x" — strip the extension for folder-based lookups.
    base_name = template_name[:-5] if template_name.lower().endswith(".docx") else template_name
    try:
        base_name = normalize_slug(base_name, label="template name")
    except ValueError as exc:
        return f"Error: {exc}"

    # Resolve template docx path
    candidates = [
        os.path.join(templates_dir, base_name, "template.docx"),
        os.path.join(templates_dir, f"{base_name}.docx"),
    ]

    docx_template_path = None
    for cand in candidates:
        if os.path.exists(cand):
            docx_template_path = cand
            break

    if not docx_template_path:
        return f"Error: Template '{template_name}' not found. Searched paths:\n" + "\n".join(f"- {c}" for c in candidates)

    # template.yaml (if present alongside template.docx) declares the fields
    # this template actually expects -- use them as required_fields so a
    # forgotten field surfaces as a real, reported issue instead of silently
    # shipping a "[Field Required]" placeholder no one notices.
    required_fields = None
    yaml_path = os.path.join(os.path.dirname(docx_template_path), "template.yaml")
    if os.path.exists(yaml_path):
        try:
            with open(yaml_path) as f:
                tpl_meta = yaml.safe_load(f) or {}
            fields = tpl_meta.get("fields")
            if fields:
                required_fields = list(fields.keys())
        except Exception:
            pass

    if not output_name:
        client_clean = context.get("client_name", "document").lower().replace(" ", "_")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        clean_tpl_name = base_name
        output_name = f"{client_clean}_{clean_tpl_name}_{timestamp}"

    output_name = sanitize_output_basename(output_name)

    if not output_format:
        output_format = config.get("default_output_format", "docx")

    output_docx_path = resolve_within(output_dir, f"{output_name}.docx")
    convert_pdf = (output_format.lower() == "pdf")

    try:
        engine = DocumentEngine(docx_template_path)
        res = engine.generate(
            context=context,
            output_path=output_docx_path,
            include_toc=include_toc,
            convert_to_pdf=convert_pdf,
            required_fields=required_fields,
        )

        docx_out = res.get("docx_path")
        pdf_out = res.get("pdf_path")
        issues = res.get("issues") or {}

        if res.get("status") == "issues_found":
            lines = [f"ISSUES FOUND — do not treat this document as finished.\n- Word Document: {docx_out}"]
            if issues.get("structural_error"):
                lines.append(f"- Structural error re-opening the saved file: {issues['structural_error']}")
            if issues.get("unrendered_tags"):
                lines.append(f"- Unrendered template tag(s) still in the document text: "
                            f"{', '.join(issues['unrendered_tags'][:10])} "
                            f"— check for a field name typo or a tag Word split across formatting runs.")
            if issues.get("missing_fields"):
                lines.append(f"- Field(s) with no value given, filled with a visible placeholder instead: "
                            f"{', '.join(issues['missing_fields'])} — this document is not ready to file/send "
                            f"until these are supplied and it's re-rendered.")
            return "\n".join(lines)

        msg = f"Success! Document generated successfully.\n- Word Document: {docx_out}"
        if pdf_out:
            msg += f"\n- PDF Document: {pdf_out}"
        elif convert_pdf:
            msg += "\n- (PDF conversion failed or LibreOffice soffice not available; DOCX saved successfully)."

        return msg
    except Exception as e:
        return f"Error executing populate_template: {e}"

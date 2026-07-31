import os

def _find_aimaos_root():
    p = os.path.dirname(os.path.abspath(__file__))
    while p != os.path.dirname(p) and not os.path.exists(os.path.join(p, "aimaos_config.yaml")):
        p = os.path.dirname(p)
    return p
AIMAOS_ROOT = os.environ.get("AIMAOS_ROOT") or _find_aimaos_root()
import sys
import json
import importlib.util
from datetime import datetime

REPORTS_DIR = os.path.join(AIMAOS_ROOT, "Quinn-AI/workspace/reports")

# Kai owns case-record organization — loaded by file path, not `sys.path.insert`
# + package import, because Kai-AI's `business` package is a namespace package
# (no __init__.py) that would collide with any other agent's own `business`
# package inserted on sys.path. Same pattern as Alix's dispatch_document.py.
_client_file_spec = importlib.util.spec_from_file_location(
    "kai_client_file", os.path.join(AIMAOS_ROOT, "Kai-AI/business/client_file.py"))
client_file = importlib.util.module_from_spec(_client_file_spec)
_client_file_spec.loader.exec_module(client_file)

TOOL_DEFINITION = {
    "name": "research_brief",
    "description": "Generates a structured research briefing report synthesizing background literature, legal statutes, and domain facts for a given topic or query. Pass client_name when the research is for a specific client's matter so the report lands in that case's own folder instead of Quinn's general workspace.",
    "parameters": {
        "type": "object",
        "properties": {
            "topic": {
                "type": "string",
                "description": "Topic or query to research (e.g. 'Florida Statute 68.07 Name Change Requirements')."
            },
            "scope": {
                "type": "string",
                "description": "Scope of research ('statutory', 'case_law', 'procedural', 'general')."
            },
            "client_name": {
                "type": "string",
                "description": "Optional: give this whenever the research is for a specific client's "
                               "matter (not general office research) — must match what other agents use "
                               "(populate_template, dispatch_document, manage_case_records) so the brief "
                               "lands in that same case's folder rather than Quinn's own workspace."
            }
        },
        "required": ["topic"]
    }
}


def _generate_brief_body(topic, scope):
    """Asks Quinn's local model for topic-specific research content.
    Returns (body_text, model_tag). Raises on LLM failure."""
    sys.path.insert(0, AIMAOS_ROOT)
    from core.llm import LLMClient
    from core.office_agent import load_office_config

    office_cfg = load_office_config()
    llm_cfg = dict(office_cfg.get("llm", {}))
    quinn_cfg = office_cfg.get("agents", {}).get("Quinn", {})
    # Prefer the dedicated prose model: brief writing is a plain text call,
    # so it can use models that lack Ollama tool-calling support.
    llm_cfg["model"] = (quinn_cfg.get("research_model")
                       or quinn_cfg.get("model")
                       or llm_cfg.get("default_model", "qwen3.5:2b"))
    client = LLMClient({"llm": llm_cfg})

    prompt = (
        f"Write a concise legal research briefing on: {topic}\n"
        f"Scope: {scope}. Jurisdiction context: Florida (2nd, 4th, and 7th Judicial Circuits).\n\n"
        "Structure exactly as:\n"
        "## Executive Summary\n(2-3 sentences specific to this topic)\n"
        "## Core Findings & Citations\n(numbered list: governing statutes/rules with chapter numbers, "
        "mandatory requirements, notable exceptions)\n"
        "## Procedural Workflow\n(numbered filing steps, including relevant Florida Family Law form numbers when applicable)\n"
        "## Recommendations for Document Agent (Alix)\n(fields and documents Alix must collect or prepare)\n\n"
        "Be specific to the topic. If you are uncertain about a citation, mark it '[verify]'. "
        "Do not include any preamble before the first heading."
    )
    resp = client.chat([
        {"role": "system",
         "content": "You are Quinn, the Research & Legal Intelligence Reporter in AIMAOS, "
                    "an offline legal-office assistant. You write precise, structured briefings."},
        {"role": "user", "content": prompt},
    ])
    body = (resp.content or "").strip()
    if not body:
        raise RuntimeError("model returned empty briefing")
    return body, llm_cfg["model"]


def execute(topic, scope="statutory", client_name=None):
    report_filename = f"brief_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.md"
    # Only file into a case's own folder if that case genuinely already
    # exists -- resolve_client_dir would happily create a brand-new,
    # state-less directory otherwise, which is exactly the kind of orphaned
    # entry client_file.audit_records() exists to catch.
    filing_for_case = bool(client_name) and client_file.client_exists(client_name)
    if filing_for_case:
        case_dir = client_file.resolve_client_dir(client_name)
        reports_dir = os.path.join(case_dir, "research")
    else:
        reports_dir = REPORTS_DIR
    os.makedirs(reports_dir, exist_ok=True)
    report_path = os.path.join(reports_dir, report_filename)

    try:
        body, model = _generate_brief_body(topic, scope)
        provenance = f"Synthesized by Quinn via local model `{model}`."
        status_note = ""
    except Exception as e:
        # Honest fallback: never present canned text as research.
        body = ("## Executive Summary\n"
                f"RESEARCH UNAVAILABLE: the local research model could not be reached ({e}). "
                "This placeholder contains NO topic-specific findings and must not be "
                "relied on. Re-run once the local LLM backend is available.\n")
        provenance = "PLACEHOLDER — no model-generated content."
        status_note = " (PLACEHOLDER: local model unavailable)"

    content = f"""# Research Briefing: {topic}
*Scope*: {scope}
*Generated*: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} by **Quinn (Research Agent)** — {provenance}

{body}
"""
    with open(report_path, "w") as f:
        f.write(content)

    first_finding = next((l.strip("-*# ").strip() for l in body.splitlines()
                          if l.strip() and not l.strip().startswith("#")), "see report")

    case_note = ""
    if filing_for_case:
        client_file.log_entry(
            client_name, f"Quinn produced a research briefing on '{topic}' -> {report_path}")
        case_note = f"\n- Filed in case record for {client_name}"
    elif client_name:
        case_note = (f"\n- Note: no case record exists yet for {client_name}; saved to Quinn's "
                    f"general workspace instead. Ask Kai to open a case first if this is real client work.")

    return (f"Research briefing compiled{status_note}.\n"
            f"- Saved Report: {report_path}\n"
            f"- Lead Finding: {first_finding[:200]}{case_note}")

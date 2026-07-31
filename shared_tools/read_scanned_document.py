"""Reads a scanned image or image-based PDF page, shared by every AIMAOS
agent. No OCR library needed — routes through a local vision-capable Ollama
model (gemma3 by default, confirmed installed with vision capability) that
reads the page directly, which handles messy real-world scans (IDs,
certificates, photographed forms) better than traditional OCR anyway.

This is the fix for a real gap: the standard read_document.py text
extraction only pulls PDF text layers, which scanned documents don't have,
and no OCR library (pytesseract/tesseract) is installed in this offline
environment. Vision-model reading sidesteps that dependency entirely.

Env var:
  VISION_MODEL   optional — Ollama model tag to use (default: gemma3:4b).
                Must be a model with vision capability (`ollama show
                <model>` lists "vision" under capabilities).
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
import base64

sys.path.insert(0, AIMAOS_ROOT)
from core.llm import LLMClient
from core.office_agent import load_office_config

DEFAULT_VISION_MODEL = "gemma3:4b"
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff")
PDF_RENDER_DPI = 200

TOOL_DEFINITION = {
    "name": "read_scanned_document",
    "description": "Reads a scanned image or image-based PDF page using a local vision-capable model — "
                   "for documents with no text layer (IDs, certificates, photographed forms) where "
                   "normal text extraction returns nothing. Returns a transcription or specific "
                   "extracted fields.",
    "parameters": {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Absolute path to an image file or a PDF."
            },
            "page": {
                "type": "integer",
                "description": "1-indexed PDF page to read (default 1). Ignored for image files."
            },
            "extract_fields": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Specific field names to extract, e.g. ['full_name', 'date_of_birth', "
                               "'document_number']. Omit for a full plain-text transcription instead."
            },
            "instructions": {
                "type": "string",
                "description": "Extra context to help the model, e.g. 'this is a Florida driver's license'."
            }
        },
        "required": ["file_path"]
    }
}


def _load_image_bytes(file_path, page):
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".pdf":
        import fitz
        doc = fitz.open(file_path)
        try:
            if page < 1 or page > doc.page_count:
                raise ValueError(f"page {page} out of range (document has {doc.page_count} page(s))")
            pix = doc[page - 1].get_pixmap(dpi=PDF_RENDER_DPI)
            return pix.tobytes("png")
        finally:
            doc.close()
    if ext in IMAGE_EXTENSIONS:
        with open(file_path, "rb") as f:
            return f.read()
    raise ValueError(f"Unsupported file type '{ext}'. Use an image ({', '.join(IMAGE_EXTENSIONS)}) or a PDF.")


def _build_llm():
    office_cfg = load_office_config()
    llm_cfg = dict(office_cfg.get("llm", {}))
    llm_cfg["model"] = os.environ.get("VISION_MODEL", DEFAULT_VISION_MODEL)
    return LLMClient({"llm": llm_cfg})


def _strip_code_fence(text):
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


def execute(file_path, page=1, extract_fields=None, instructions=None):
    if not file_path or not os.path.isfile(file_path):
        return f"Error: file not found: {file_path}"

    try:
        image_bytes = _load_image_bytes(file_path, page)
    except Exception as e:
        return f"Error reading '{file_path}': {e}"

    b64 = base64.b64encode(image_bytes).decode("ascii")

    if extract_fields:
        prompt = (
            "Extract the following fields from this document image and respond with ONLY a JSON "
            f"object using exactly these keys: {json.dumps(list(extract_fields))}. "
            "If a field is not visible or not present, use null for its value. No extra text, "
            "no markdown, just the JSON object."
        )
    else:
        prompt = "Transcribe all visible text in this document image exactly as it appears."
    if instructions:
        prompt += f"\n\nContext: {instructions}"

    try:
        llm = _build_llm()
        resp = llm.chat([{"role": "user", "content": prompt, "images": [b64]}])
    except Exception as e:
        return f"Vision model call failed: {e}"

    content = (resp.content or "").strip()
    if not content:
        return "Vision model returned no content — the image may be unreadable or the model may not support vision."

    if extract_fields:
        try:
            parsed = json.loads(_strip_code_fence(content))
            return json.dumps(parsed, indent=2)
        except (ValueError, json.JSONDecodeError):
            return f"(model reply was not valid JSON, returning raw text)\n{content}"

    return content

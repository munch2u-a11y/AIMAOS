# Technical Audit: Alix-AI (Document Production & Keeper Agent)

## 1. Agent Overview
- **Workspace**: `/path/to/AIMAOS/Alix-AI`
- **Primary Function**: Intake form processing, Jinja2 Word template rendering, context validation, dynamic Table of Contents (TOC) XML injection, PDF compilation, and outbound client package dispatch.

---

## 2. Core Modules & Code Citations

### 2.1. Document Engine (`core/document_engine.py`)
Renders legal context data into Jinja2-tagged Microsoft Word `.docx` templates using `docxtpl`.

```python
class DocumentEngine:
    def __init__(self, template_path):
        self.template_path = os.path.abspath(template_path)

    def generate(self, context, output_path, convert_pdf=False):
        doc = DocxTemplate(self.template_path)
        doc.render(context)
        doc.save(output_path)
```

- **TOC Injection (`_add_toc`)**: Injects low-level OpenXML elements (`w:fldChar`, `w:instrText`) into Word document paragraphs to generate native Word Table of Contents fields.
- **PDF Conversion (`_convert_to_pdf`)**: Invokes LibreOffice (`soffice --headless --convert-to pdf`) to produce production PDF court filings.

### 2.2. Template Reviewer Subagent (`core/subagents/template_reviewer.py`)
Designed for local 2B–8B parameter LLMs:
- Evaluates legal `.docx` templates in **20-paragraph token-bounded windows** (`CHUNK_PARAGRAPH_SIZE = 20`, ~300-500 tokens per call).
- Audits templates to ensure all blank underlines (`_______`) are converted to Jinja2 tags (e.g. `{{ client_name }}`).

### 2.3. Email Connector (`core/watchers/email_connector.py`)
- Dispatches completed legal document packages, identified next steps, and statutory summaries to client email recipients (`helix.agi.system@gmail.com`).
- Logs outbound dispatches to `/path/to/AIMAOS/Alix-AI/workspace/output/outbound_email_log.json`.

---

## 3. Supported Florida Court Templates
1. `form_12_982_a`: Adult Name Change Petition
2. `form_12_982_b`: Adult Name Change Final Judgment
3. `form_12_982_f`: Minor Child Name Change Petition
4. `form_12_901_a`: Joint Petition for Simplified Dissolution of Marriage
5. `form_12_902_c`: Family Law Financial Affidavit (Long Form)
6. `form_12_902_e`: Child Support Guidelines Worksheet

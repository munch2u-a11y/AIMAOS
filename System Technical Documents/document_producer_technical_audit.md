# Technical Audit: Document Producer & Keeper Agent (Alix Preset)

## 1. Agent Overview
- **Workspace**: `<office root>/Alix-AI`
- **Primary Function**: Intake form processing, Jinja2 Word template rendering, legal template library cataloging, context validation, dynamic Table of Contents (TOC) XML injection, PDF compilation, and outbound client package dispatch.

---

## 2. Core Modules & Code Citations

### 2.1. Template Cataloger Tool (`tools/catalog_templates.py`)
Indexes legal templates across practice area directories (`Alix-AI/templates/`), extracts file metadata, and updates `template_registry.json` and SQLite `templates` table records.

```python
def scan_and_index_templates(templates_dir="<office root>/Alix-AI/templates"):
    # Walks practice area template directories (family_law, estate_planning, guardianship, probate, name_change)
    # Extracts file size, modifications, and category mappings
    # Updates template_registry.json and relational database
```

### 2.2. Document Engine (`business/document_engine.py`)
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

### 2.3. Template Reviewer Subagent (`business/subagents/template_reviewer.py`)
Designed for local 2B–8B parameter LLMs:
- Evaluates legal `.docx` templates in **20-paragraph token-bounded windows** (`CHUNK_PARAGRAPH_SIZE = 20`, ~300-500 tokens per call).
- Audits templates to ensure all blank underlines (`_______`) are converted to Jinja2 tags (e.g. `{{ client_name }}`).

### 2.4. Email Connector (`business/watchers/email_connector.py`)
- Dispatches completed legal document packages, identified next steps, and statutory summaries to client email recipients.
- Logs outbound dispatches to `<office root>/Alix-AI/workspace/output/outbound_email_log.json`.

---

## 3. Practice Area Template Categories
1. **Family Law**: Simplified Dissolution of Marriage, Financial Affidavit, Child Support Guidelines
2. **Name Change**: Adult Name Change Petition & Final Judgment, Minor Name Change Petition
3. **Estate Planning**: DPOA Letters of Authority, Last Will & Testament, Revocable Trust Templates
4. **Probate**: Affidavit of Heirs, Petition for Probate Administration
5. **Guardianship**: Letters of Guardian Advocate, Guardian Intakes
6. **Housing & Notices**: 3-Day Eviction Notice, Notice of Hearing

---

## 4. Capabilities & Delegation Schema
- **Capabilities Config**: `Alix-AI/capabilities.yaml`
- **Domains**: `file_research`, `document_production`, `memory_and_skills`, `office_comms`, `voice_intake`, `scanned_document_intake`
- **Registered Tools by Domain**:
  - `file_research`: `browse_files`, `search_files`, `list_files`, `read_document`
  - `document_production`: `populate_template`, `write_document`, `dispatch_document`, `review_templates`, `catalog_templates`, `edit_image`, `assemble_pdf`
  - `memory_and_skills`: `manage_memory`, `manage_skills`, `ingest_document`, `run_script`
  - `office_comms`: `ask_agent`, `draft_client_request`
  - `voice_intake`: `speech_to_text`, `text_to_speech`
  - `scanned_document_intake`: `read_scanned_document`

Alix reasons over these **domains**, not over raw tool schemas: each turn it
delegates a directive to a domain orchestrator, which selects and briefs the
specific tool subagent. See `core/delegation.py`.

> Alix also ships an interactive CLI (`Alix-AI/main.py`) that runs a
> conventional direct tool loop against the same tool set, for hands-on use
> outside the autonomous daemon.

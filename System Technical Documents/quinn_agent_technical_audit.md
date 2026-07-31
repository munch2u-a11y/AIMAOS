# Technical Audit: Quinn-AI (Research & Legal Intelligence Reporter)

## 1. Agent Overview
- **Workspace**: `<office root>/Quinn-AI`
- **Primary Function**: Statutory legal research, case law analysis, procedural rule verification, and legal briefing report synthesis.
- **Model Profile**: Dual model architecture:
  - Agent Turn Loop: `qwen3.5:2b` (tool-calling capable)
  - Prose Brief Writing: `gemma3:4b` (high-quality legal prose generation)

---

## 2. Core Modules & Code Citations

### 2.1. Research Briefing Synthesis Engine (`tools/research_brief.py`)
Generates structured legal research briefings for Florida Judicial Circuits (2nd, 4th, 7th) covering Florida Family Law Rules of Procedure and Florida Statutes (Chapter 68 adult name changes, Chapter 744 guardianship, Chapter 61 dissolution of marriage, Chapter 83 eviction & landlord-tenant notices).

```python
def generate_research_brief(topic, jurisdiction="Florida 4th Judicial Circuit", statutory_references=None):
    # 1. Queries local reference materials (<office root>/workspace/reference_materials/)
    # 2. Analyzes statutory constraints, filing deadlines, and jurisdictional rules
    # 3. Uses gemma3:4b to synthesize formal legal research memorandum
```

### 2.2. Legal Reference Library Integration
- Reads reference manuals stored in `<office root>/workspace/reference_materials/` (including `FL Rules of Civ Pro.pdf`).
- Formats statutory citations and procedural requirements into standard legal memo structures.

---

## 3. Capabilities & Capabilities Schema
- **Domains**: `file_research`, `research`, `web_research`
- **Capabilities Config**: `Quinn-AI/capabilities.yaml`
- **Registered Tools**:
  - `research_brief`: Generates a research brief for a topic via the configured prose model, writing markdown to the reports workspace. When the model is unreachable it writes an explicitly labelled PLACEHOLDER rather than presenting canned text as research.
  - `web_search`, `web_fetch`, `rss_feed_read`: Optional online research tools (inactive in a fully offline install).

> Statutory citations produced by a small local model carry `[verify]` markers
> and must be checked against the official sources before any filing or client
> use. Briefs are drafting aids, not legal authority.

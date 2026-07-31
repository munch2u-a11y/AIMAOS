# AIMAOS — Privacy-Scrubbed Example Artifacts & Workflows

This directory contains anonymized, synthetic examples demonstrating how **AIMAOS** manages client case records, evolves skills through Helix background reflections, and renders document templates.

> [!IMPORTANT]
> **Privacy Guarantee**: All names, dates, addresses, and case numbers in this directory are 100% synthetic fictional data (e.g. *"Alex Montgomery"*, *"2026-DR-0000"*). No actual client or personal data is present.

---

## 📁 Included Examples

1. **`examples/case_summaries/`**:
   - [`sample_client_alex_montgomery/CLIENT_FILE.md`](case_summaries/sample_client_alex_montgomery/CLIENT_FILE.md): A human-readable case summary automatically generated and maintained by a dedicated `CaseAgent`. Shows live status overviews, timeline milestones, required document checklists, and activity audit trails.
   - [`sample_client_alex_montgomery/.client_file_state.json`](case_summaries/sample_client_alex_montgomery/.client_file_state.json): The corresponding structured JSON state file.

2. **`examples/learned_skills/`**:
   - [`skills.json`](learned_skills/skills.json): Example of dynamic skill beliefs synthesized during background Helix mRAG reflection cycles based on agent execution patterns and user preferences.

3. **`examples/templates/`**:
   - [`form_petition_name_change/template.yaml`](templates/form_petition_name_change/template.yaml): Anonymized Jinja2 document template configuration and field schema.
   - [`form_petition_name_change/sample_filled_output.txt`](templates/form_petition_name_change/sample_filled_output.txt): Rendered output text showing populated context fields.

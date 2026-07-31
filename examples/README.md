# AIMAOS — Privacy-Scrubbed Example Artifacts & Workflows

This directory contains anonymized, synthetic examples demonstrating how **AIMAOS** manages client project & case records, evolves skills through Helix background reflections, and renders document templates across diverse business domains.

> [!IMPORTANT]
> **Privacy Guarantee**: All names, dates, addresses, and project/case numbers in this directory are 100% synthetic fictional data (e.g. *"Acme Logistics Solutions"*, *"Alex Montgomery"*, *"2026-CONSULT-042"*). No actual client or personal data is present.

---

## 📁 Included Examples

### 1. Business Consulting & Operations Example (`examples/consulting_project/`)
Demonstrates how AIMAOS abstracts cleanly to general small-business consulting, operations auditing, and management reporting:
- [`PROJECT_FILE.md`](consulting_project/PROJECT_FILE.md): Project summary maintained by a dedicated `CaseAgent` showing operational milestones, deliverable checklists, and activity logs.
- [`project_state.json`](consulting_project/project_state.json): Structured JSON state file for project tracking.
- [`research_brief.txt`](consulting_project/research_brief.txt): Subject matter research brief synthesized by the Research Specialist (`Quinn`).
- [`client_report_template.jinja2`](consulting_project/client_report_template.jinja2) & [`client_report_template.yaml`](consulting_project/client_report_template.yaml): Complete Jinja2 template and context mapping schema for executive consulting reports.
- [`sample_rendered_report.txt`](consulting_project/sample_rendered_report.txt): 100% reproducible rendered deliverable report.

---

### 2. Legal / Administrative Case Example (`examples/case_summaries/`)
Demonstrates legal & administrative case record management:
- [`sample_client_alex_montgomery/CLIENT_FILE.md`](case_summaries/sample_client_alex_montgomery/CLIENT_FILE.md): Human-readable case summary maintained by `CaseAgent`.
- [`sample_client_alex_montgomery/.client_file_state.json`](case_summaries/sample_client_alex_montgomery/.client_file_state.json): Corresponding structured JSON state file.

---

### 3. Learned Skill Belief Stores (`examples/learned_skills/`)
- [`raw_belief_store_skills.json`](learned_skills/raw_belief_store_skills.json): Authentic, privacy-scrubbed raw belief store artifact preserving the exact runtime schema of `BeliefStore` (`belief_id`, `category`, `content`, `confidence`, `stability_index`, `verifications`, `access_count`, `relations`, `memory_refs`, `tags`, `conceptual_tags`, `relevance`, `weight`, `created_at`, `updated_at`).
- [`exported_skills.json`](learned_skills/exported_skills.json): A high-level, human-readable skill export format transformed for product-facing displays.

---

### 4. Template Reproducibility Example (`examples/templates/`)
- [`form_petition_name_change/template.jinja2`](templates/form_petition_name_change/template.jinja2): Source Jinja2 template text.
- [`form_petition_name_change/template.yaml`](templates/form_petition_name_change/template.yaml): Complete template metadata and context mapping schema.
- [`form_petition_name_change/sample_filled_output.txt`](templates/form_petition_name_change/sample_filled_output.txt): Rendered text produced by evaluating `template.jinja2` with `template.yaml`'s default context.

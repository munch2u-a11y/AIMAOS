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
   - [`raw_belief_store_skills.json`](learned_skills/raw_belief_store_skills.json): Authentic, privacy-scrubbed raw belief store artifact preserving the exact runtime schema of `BeliefStore` (`belief_id`, `category`, `content`, `confidence`, `stability_index`, `verifications`, `access_count`, `relations`, `memory_refs`, `tags`, `conceptual_tags`, `relevance`, `weight`, `created_at`, `updated_at`).
   - [`exported_skills.json`](learned_skills/exported_skills.json): A high-level, human-readable skill export format transformed for product-facing displays.

3. **`examples/templates/`**:
   - [`form_petition_name_change/template.jinja2`](templates/form_petition_name_change/template.jinja2): The source Jinja2 template text.
   - [`form_petition_name_change/template.yaml`](templates/form_petition_name_change/template.yaml): Complete template metadata and default context schema mapping all 9 context variables (`client_name`, `street_address`, `city`, `county`, `zip_code`, `new_name`, `circuit_number`, `case_number`, `filing_date`).
   - [`form_petition_name_change/sample_filled_output.txt`](templates/form_petition_name_change/sample_filled_output.txt): 100% reproducible rendered text produced by evaluating `template.jinja2` with `template.yaml`'s default context.

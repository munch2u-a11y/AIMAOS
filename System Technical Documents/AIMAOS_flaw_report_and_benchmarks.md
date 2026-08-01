# AIMAOS Public-Beta Release Audit and Known Gaps

**Review date:** 2026-07-31
**Scope:** current tracked tree, reachable local Git history, public documentation, isolated release tests, and source-level architecture review.

This document replaces earlier phase-by-phase benchmark notes that described intermediate builds and machine-specific test runs. Those notes were useful during development but were not an accurate description of the current public-beta source.

## 1. Release assessment

The current tree contains a functional local workstation, persistent jobs, an autonomous office daemon, deterministic advancement review, matter/file navigation, template-driven draft generation, in-app document annotations, cooperative pause/resume, and default-deny security controls.

It should still be described as a beta. The remaining launch risks are operational and trust-related: public Git-history sanitation, authoritative template provenance, clean-install validation, backup/restore rehearsal, accessibility testing, Android hardening, and the unavoidable limits of small-model output.

## 2. Privacy and repository audit

### Current tracked tree

Automated and manual checks cover:

- high-confidence API/token/private-key patterns;
- credential assignments and environment-variable usage;
- email, SSN-like, local-home-path, and case-name patterns;
- tracked files with sensitive names;
- DOCX embedded XML and author metadata;
- ignored runtime boundaries;
- public examples and test fixtures.

At the time of this review, no high-confidence secret token or private key was detected in tracked HEAD. Credential-related matches resolve to environment lookups or empty/example configuration. Public examples are explicitly marked synthetic. A case-specific test label was replaced with an unmistakably synthetic label, and tracked coding-agent guidance was removed because agent guidance is local-only.

### Reachable Git history — release blocker

Older reachable commits contain now-deleted generated workspaces and runtime artifacts, local filesystem paths, generated-output names, memory/board/report files, and personal-looking email metadata. Deleting them in a new commit does not remove the blobs from Git history.

Before representing the repository as privacy-scrubbed, the owner must approve and perform a coordinated history rewrite that:

1. removes all generated root agent workspaces and runtime directories from every commit;
2. replaces personal email/path strings in retained source history;
3. rewrites author/committer email metadata if the existing address is not intentionally public;
4. force-pushes all affected public branches/tags;
5. expires cached pull requests/releases where applicable and asks collaborators to reclone;
6. rotates any credential that may ever have appeared outside tracked source, including credentials embedded in local Git remote URLs.

Until that operation is complete and the rewritten remote is rescanned, “absolutely no private information in the public repository” cannot be guaranteed.

## 3. Documentation corrections made by this audit

The public documentation now avoids these inaccurate or overstated claims:

- “100% offline” was replaced with **local-first default**, because optional web, calendar, cloud vector, remote speech, and email integrations exist.
- “any model/backend” was narrowed to the implemented **Ollama and OpenAI-compatible llama.cpp** clients.
- “zero cost” was narrowed to **no required paid AI API subscription**; hardware and operations still cost money.
- “hardware-enforced email” was corrected to **software policy enforcement**.
- model tables now reflect the checked-in 4B defaults and Finn's 2B assignment rather than an older all-2B configuration.
- document review is described as extracted-text annotation, not a full word processor.
- research and deadline output is explicitly unverified.
- the Android project is described as an experimental AppCompat/WebView shell, not a Compose or store-ready app.
- generated live agent directories are distinguished from tracked `starter_packs/` source.
- old benchmark results are no longer presented as current release performance guarantees.

## 4. Current automated release baseline

The isolated suite under `tests/unit/` exercises security boundaries, path validation, setup, jobs/privacy, database state, workflow review, form handling, document extraction/review, UI contracts, and HTTP behavior. It does not require a live model or real client data.

Manual benchmark scripts remain available but can call real local models and mutate live office state. Their historical timings and quality scores depend on model versions, prompts, hardware, and runtime data; they are diagnostic evidence, not product guarantees.

Every release should record:

- commit identifier;
- exact effective model tags and backend;
- whether loopback HTTP tests ran or were sandbox-skipped;
- unit test count and failures/skips;
- synthetic smoke-test artifacts;
- template versions reviewed;
- any changed security flags.

## 5. Known gaps and priorities

### P0 — before public onboarding

1. **Rewrite and rescan Git history.** Current HEAD cleanup alone is insufficient.
2. **Template provenance.** Record authoritative URL, jurisdiction, form/revision date, checksum, and human review date for every bundled form.
3. **Clean-host install.** Test installation, setup, model validation, UI launch, daemon control, and uninstall/data removal on a non-developer account.
4. **Backup/restore/rollback.** Exercise consistent SQLite/runtime backups and restoration with synthetic matters.
5. **Adversarial boundary testing.** Path traversal, cross-matter access, prompt injection, malformed documents, XSS, oversized uploads, archive handling, and reverse-proxy headers.
6. **Accessibility.** Keyboard-only, screen reader, reduced motion, small screen, light/dark theme, and dialog focus testing.

### P1 — beta quality

1. Add source citations/passages to grounded assistant answers.
2. Expand exact-target human approval for any future external mutation.
3. Improve document editing through a separately reviewed native-office integration rather than pretending extraction is full fidelity.
4. Add resumable onboarding and visible model/storage health.
5. Add feedback tied to artifacts without learning raw matter content by default.
6. Add explicit schema/data migrations and versioned backup compatibility.

### P2 — later product scope

- signed installers and update verification;
- real multi-user identity, authorization, and audit review;
- connector-specific permission and data-flow controls;
- production mobile authentication/origin validation and release signing;
- spreadsheet/presentation-native review;
- packaged support, migration, export, and uninstall workflows.

## 6. Model and workflow limitations

- Small models can select the wrong tool, omit a required call, invent facts, or summarize work as complete without sufficient evidence.
- The advancement review can flag suspicious completion but does not prove correctness.
- A rendered DOCX proves rendering succeeded, not that the form is current or legally sufficient.
- A local research brief is a drafting aid; citations must be checked against authoritative sources.
- Hash-based default memory retrieval is not semantic embedding search.
- Layered delegation improves focus at the cost of many model calls and potentially long CPU runtimes.
- Optional network integrations change the privacy boundary and are disabled by default for that reason.

## 7. Stop-ship conditions

Pause public onboarding for any confirmed:

- secret, client data, or private runtime artifact in the current tree or reachable public history;
- cross-matter file access;
- external action without explicit approved policy and human authorization;
- unrecoverable matter/database corruption;
- falsely reported completion that bypasses required human review;
- authentication/CSRF/path-validation bypass;
- bundled form represented as current without verified provenance.

## 8. Honest release statement

After the P0 items are complete, AIMAOS can reasonably be described as a local-first public beta for single-operator, review-centered office workflows. It should not be described as a private hosted service, unattended professional, guaranteed deadline engine, or complete replacement for a native office suite.

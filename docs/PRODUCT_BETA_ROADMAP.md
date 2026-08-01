# Product Beta Roadmap

This roadmap separates responsible public-beta work from later office-suite scope. It uses common interaction patterns found across modern office assistants—one workspace for files and tasks, contextual assistance beside artifacts, visible sources, inline feedback, reusable workflows, and administrator-controlled data boundaries—without claiming feature parity with mature commercial suites.

## Product position

AIMAOS should make a narrower, testable promise:

> A local-first workstation that turns approved files and office requests into prioritized tasks and reviewable matter artifacts using operator-selected local models.

It should not be marketed as an infallible autonomous employee, complete office-editor replacement, secure hosted service, or legal-deadline authority.

## Implemented beta foundation

- Home, Agenda, Matters, Create, Assistant, Settings, and daemon pause/resume in one browser workstation.
- Persistent background jobs with queued, running, completed, failed, and interrupted states.
- Deterministic daily advancement review for dependencies, stale work, blockers, staff communications, and suspicious completion.
- One-click work-item navigation to a safe matter/file review target.
- Matter-scoped intake, living summaries, file lists, and typed operator notes.
- Template-driven DOCX drafts and protected fillable intake forms.
- Extracted-text document review with line annotations, note status, stale-source warning, and deduplicated correction tasks.
- Local model configuration, sequential daemon turns, layered tool delegation, and private per-agent operational memory.
- Loopback-first API, optional token, CSRF/origin checks, safe browser rendering, path/upload limits, and default-deny network/external/shell/developer policy.
- Direct communications represented as staff reminders under default policy.

## P0 — before inviting public users

1. Rewrite and rescan public Git history so no generated runtime/private artifacts or personal metadata remain reachable.
2. Test install/setup/start/pause/resume/restart on a clean non-developer Linux account.
3. Complete authoritative provenance and revision review for every bundled form.
4. Exercise backup, restore, rollback, interrupted-job recovery, retention, and deletion using synthetic data.
5. Run path traversal, cross-matter access, prompt injection, malformed document, XSS, oversized upload, and reverse-proxy tests.
6. Complete keyboard, screen-reader, reduced-motion, small-screen, light-mode, and dark-mode review.
7. Publish a private vulnerability route, support/feedback route, limitations, and stop-ship process.
8. Record supported Python, Ollama, model, LibreOffice, and OS versions for the release commit.

## P1 — make reviewed work faster and more grounded

1. **Grounded answers:** show the files and passages used for an answer and say when no support was found.
2. **Approval center:** extend exact-target review to future email drafts, file moves, calendar mutations, and other external actions.
3. **Document editing integration:** offer an opt-in, separately secured native-office bridge for selected-text rewrite and field population while preserving the current annotation audit trail.
4. **Unified local search:** search matter names, summaries, filenames, drafts, jobs, and review notes with visible scope filters.
5. **Reusable work recipes:** reviewed workflows with required inputs, expected artifacts, permissions, and failure checks.
6. **Artifact feedback:** useful/not useful, corrected outcome, failure category, and comments without learning raw matter content by default.
7. **Guided onboarding:** resumable model health, storage-root approval, synthetic sample, and privacy choices.
8. **Migrations:** schema/runtime versioning, tested upgrade/rollback, and backup compatibility.

## P2 — broader office-suite capability

- signed desktop packages and verified updates;
- multi-user identity, per-matter authorization, and audit review;
- permission-scoped calendar/mail/cloud-file connectors;
- spreadsheet and presentation-native workflows;
- production mobile app and secure remote-administration profile;
- data export, migration, uninstall, and managed retention;
- measured semantic retrieval backend with a documented privacy boundary.

## Measures that matter

- clean-install success and time to first reviewed artifact;
- job/task success, retry, interruption, and corrected-failure rates;
- percentage of answers with usable supporting evidence;
- drafts accepted, materially edited, or discarded;
- staff reminders completed/snoozed and stale blockers resolved;
- proposed external actions approved, changed, rejected, or blocked;
- privacy, cross-matter, misleading-completion, and data-loss incidents;
- median local model time and resource use by workflow.

Prompt volume and agent activity are not success metrics by themselves.

## Stop-ship conditions

Stop new onboarding for confirmed data exposure, reachable private Git history, cross-matter access, unreviewed external action, unrecoverable data loss, authentication/path-policy bypass, or a workflow that reports consequential work complete without the required evidence/review.

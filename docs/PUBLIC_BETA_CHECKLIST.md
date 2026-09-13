# Public-Beta Release Checklist

## Repository privacy

- [ ] Current tracked tree has no secret, credential, client, matter, local-path, memory, task-log, or generated-output data.
- [ ] Reachable history and all public branches/tags were scanned, not only HEAD.
- [ ] Commit author/committer emails are intentionally public or privacy-protected.
- [ ] DOCX/PDF embedded content, comments, custom properties, and author metadata were reviewed.
- [ ] Runtime workspaces, `comms/`, databases, review sidecars, local agent guidance, and credentials are ignored and absent from history.
- [ ] Any historical exposure was removed through coordinated history rewrite; affected credentials were rotated and collaborators instructed to reclone.

## Product and UX

- [ ] First-run instructions were tested on clean non-administrator Windows and unprivileged Linux accounts.
- [ ] Home, Agenda, Matters, Create, Assistant, Settings, and pause/resume are understandable without developer knowledge.
- [ ] Empty, loading, queued, running, paused, completed, interrupted, and failed states are clear.
- [ ] Clickable review tasks open the exact safe file or fall back to the correct matter.
- [ ] Keyboard navigation, dialog focus, screen reader, reduced motion, mobile layout, light mode, and dark mode were reviewed.
- [ ] No browser response exposes absolute paths, raw stack traces, secrets, raw task arguments, or private memory.
- [ ] Every document/research workflow labels output as a draft requiring review.
- [ ] Browser document review is described as text-oriented, not full native-office fidelity.

## Templates and professional use

- [ ] Every bundled template has authoritative source, jurisdiction, revision date, checksum, and human review date.
- [ ] Representative DOCX/PDF renders were visually inspected.
- [ ] Intake templates are not confused with court-ready filing templates.
- [ ] Citations, extracted dates, deadlines, and model-written summaries require authoritative verification.
- [ ] No production-critical workflow depends exclusively on AIMAOS output.

## Security and privacy

- [ ] Dashboard is loopback-only or behind an authenticated TLS reverse proxy.
- [ ] Native file opening is disabled for remote-browser deployments.
- [ ] Developer, network, shell, external-mutation, document-delegation, raw-log, and raw-memory flags are off.
- [ ] Email is `READ_ONLY`; direct communications are staff reminders.
- [ ] Storage roots are narrow and approved.
- [ ] Runtime account is unprivileged and uses encrypted storage and backups.
- [ ] Prompt-injection, path-traversal, cross-matter, malformed-document, oversized-upload, XSS, and origin/CSRF cases were tested.
- [ ] Retention, deletion, incident, and private vulnerability-reporting procedures were exercised.

## Reliability and deployment

- [ ] The native virtual-environment Python runs `doctor.py` with no failures on Windows and Linux.
- [ ] The native virtual-environment Python runs `pytest -q` successfully on Windows and Linux, including loopback HTTP tests.
- [ ] JavaScript syntax and Python compilation checks pass.
- [ ] Effective model/backend tags and tool-calling support are recorded from the running host.
- [ ] Clean start, pause after current turn, resume, stopped-daemon start, restart, and duplicate-daemon prevention were tested.
- [ ] Job interruption, task lease/retry, backup, restore, and rollback were tested with synthetic data.
- [ ] Supported OS, Python, Ollama, model, LibreOffice, and dependency versions are recorded.
- [ ] Release diff, dependency locks, migrations, and rollback copy were reviewed.

## Beta operations

- [ ] Users received privacy, backup, limitations, human-review, and optional-network guidance.
- [ ] A support/feedback channel and stop-ship owner are assigned.
- [ ] Success measures are based on reviewed artifacts and resolved work, not prompt volume.
- [ ] Android is not represented as supported production access until its separate security checklist passes.

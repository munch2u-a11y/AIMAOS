# Public-Beta Release Checklist

## Product and UX

- [ ] First-run instructions were tested on a clean Linux account.
- [ ] Empty, loading, completed, interrupted, and failed job states are understandable.
- [ ] Keyboard navigation, visible focus, mobile layout, light mode, and dark mode were reviewed.
- [ ] No browser response exposes absolute paths, raw stack traces, or secrets.
- [ ] Every document workflow labels output as a draft requiring review.
- [ ] Template jurisdiction, source, revision, and review date are complete or visibly flagged.

## Security and privacy

- [ ] Dashboard is loopback-only or behind an authenticated TLS reverse proxy.
- [ ] Native file opening is disabled for remote-browser deployments.
- [ ] Developer, network, shell, external-mutation, and document-delegation flags are off.
- [ ] Storage roots are narrow and approved.
- [ ] Runtime account is unprivileged and uses encrypted storage and backups.
- [ ] Synthetic prompt-injection, path-traversal, oversize-upload, and XSS cases were tested.
- [ ] Incident and vulnerability-reporting contacts are documented privately.
- [ ] Retention and deletion procedures were exercised.

## Reliability and deployment

- [ ] `python3 doctor.py` has no failures.
- [ ] `python3 -m pytest` passes.
- [ ] JavaScript syntax validation passes.
- [ ] Clean install, start, daemon stop, restart, job interruption, backup, and restore were tested.
- [ ] Supported OS, Python, model, Ollama, and LibreOffice versions are recorded.
- [ ] Release commit and dependency pins are reviewed.
- [ ] A rollback rehearsal succeeded.

## Beta operations

- [ ] Beta users received limitations, privacy, backup, and human-review guidance.
- [ ] A support channel and feedback intake are available.
- [ ] No production-critical workflow depends exclusively on AIMAOS output.
- [ ] Success metrics and stop-ship criteria are defined before onboarding users.

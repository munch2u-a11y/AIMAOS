# Privacy Notes

AIMAOS is local-first, but local software is not automatically private. Anyone with access to the operating-system account, work directories, backups, swap, or an exposed dashboard may be able to read office data.

## Default data behavior

- Matter files and generated work remain under local approved storage roots.
- The application does not include product analytics or crash telemetry.
- Raw tool outputs are not persisted in tool logs by default; a digest and character count are retained for diagnostics.
- Common SSN, payment-number, and email patterns are redacted from learned operational memories and recorded job failures.
- Raw memory is not injected across tasks by default.
- Matter content is not promoted into shared learned skills by default.
- Runtime tool logs and read-message markers are pruned after 30 days by the managed daemon.

Redaction is heuristic and is not a data-loss-prevention guarantee. Matter summaries, source documents, SQLite records, and office-board tasks may still contain personal information required for the workflow.

## Operator responsibilities

- Obtain permission before importing personal or confidential data.
- Use full-disk encryption and an encrypted backup destination.
- Restrict OS permissions and do not share the service account.
- Establish a retention schedule for matter files and backups.
- Stop the service and securely remove all copies when fulfilling a deletion request.
- Do not enable raw logging in production unless the need and retention period are documented.

## Data locations

- Matter work: generated `*-AI/workspace/` directories.
- Task and matter index: `comms/office_database.sqlite`.
- Compatibility board and IPC: `comms/`.
- Local reminders and daily review state: generated `Marley-AI/workspace/calendar/` and `Marley-AI/workspace/workflow_review.json`.
- Document annotations: `.aimaos_review_notes.json` and `AIMAOS_REVIEW_NOTES.md` inside the applicable matter directory.
- Private agent memories: generated agent `workspace/.memory/` directories.
- Optional email credentials: `~/.config/aimaos/credentials.env`.

These paths are excluded from git, but backups and filesystem snapshots must be governed separately.

# Operations and JSON contract

## Commands

```text
python scripts/manage_case_specialist.py initialize --case <path-or-id>
python scripts/manage_case_specialist.py refresh --case <path-or-id>
python scripts/manage_case_specialist.py status --case <path-or-id>
python scripts/manage_case_specialist.py audit --case <path-or-id>
python scripts/manage_case_specialist.py dry-run --case <path-or-id>
```

The script locates the AIMAOS repository from `--aimaos-root`, `AIMAOS_ROOT`, or the current directory. It emits one JSON object and exits nonzero on an error.

## Stable response fields

- `case_id`: normalized matter identifier.
- `status`: `initialized`, `current`, `dirty`, `unchanged`, `dry_run`, `applied`, or `attention_required`.
- `changes`: prior/current digest plus added, modified, deleted, and ignored/inventory warnings.
- `overview_fields`: fields applied to the overview record.
- `posted_tasks`, `dropped_tasks`: internal assignment outcomes.
- `verification_tasks`: staff tasks created for candidate dates.
- `queued_digest`, `in_flight_digest`, `last_error`: retry and failure state returned by status/audit.
- `warnings`: suppressed communications, rejected assignments, parser limits, or other nonfatal findings.

## State and retry behavior

The engine stores its private state in `.case_agent/change_state.json` beside the existing `.case_agent/mrag_data/` memory. It fingerprints relative path, size, modification time, and SHA-256, and excludes hidden/runtime state, rendered overview files, and temporary files.

Only one review may hold `.case_agent/review.lock`. A stale lock is recovered after 15 minutes. A file change during review makes the proposal stale and leaves the digest queued. Review failures retain the previous overview and remain retryable on the next refresh.

An identical successful digest is not reviewed again unless `--force` is explicitly supplied. Posted actions are keyed by case, digest, assignee, and normalized action so retries do not duplicate assignments.

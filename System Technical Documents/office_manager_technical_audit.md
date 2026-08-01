# Technical Audit: Office Manager and Scheduler (Marley Preset)

**Tracked source:** [`starter_packs/document_heavy/Marley-AI/`](../starter_packs/document_heavy/Marley-AI/)
**Live workspace after setup:** `<office root>/Marley-AI/`
**Configured model:** `qwen3.5:4b` in the checked-in example configuration.

## Role

Marley runs the autonomous daemon pulse, serializes daemon-managed agent turns, maintains task leases/retries, performs deterministic advancement review, manages the local calendar tool, and exposes cooperative pause/resume state to the workstation.

## Daemon cycle

[`core/office_daemon.py`](../starter_packs/document_heavy/Marley-AI/core/office_daemon.py) performs:

1. expired-lease and retry hygiene;
2. each agent's IPC inbox processing;
3. scheduled daily advancement review;
4. selection of one queued task by priority;
5. one assigned role-agent turn;
6. periodic reflection;
7. idle backoff.

`core/orchestrator.py` orders `CRITICAL`, `HIGH`, `NORMAL`, then `BACKGROUND` and excludes already dispatched work from new dispatch selection. The shared OfficeBoard also sorts each agent's own pending list by this order. Current priority is categorical; documentation should not imply a sophisticated predictive load balancer.

## Advancement and Agenda

The root [`core/workflow_review.py`](../core/workflow_review.py) is deterministic. It builds staff reminders, stale/overdue flags, dependency blockers, completion-review items, matter next steps, and safe navigation metadata. Communication tasks become staff-owned follow-ups when `workflow.direct_communications` is false.

## Calendar

[`tools/manage_schedule.py`](../starter_packs/document_heavy/Marley-AI/tools/manage_schedule.py) writes the internal `LocalCalendar`. Optional Google Calendar tooling is separately network-gated and is not a mirror/sync service unless explicitly invoked and configured.

## Pause/resume

The workstation writes an atomic pause request. Marley checks it at turn boundaries, publishes `paused`, clocks agent statuses off duty, waits without accepting another turn, and resumes when the request clears. This is cooperative rather than an immediate process kill.

## Failure behavior

- In-progress tasks receive lease timestamps and can be requeued after expiry.
- Failed tasks increment retries and are requeued or abandoned according to configuration.
- Exceptions publish degraded status rather than silently stopping the office loop.
- Dashboard jobs are a separate serialized executor; they are not scheduled by Marley.

## Limitations

- Priority labels and simple aging cannot understand every business consequence.
- Calendar extraction does not calculate or guarantee legal deadlines.
- Pause may wait for a long current model/tool turn.
- No distributed lock coordinates several daemon processes; operators must run one managed daemon.
- External calendar and communication operations remain disabled by default.

## Verification

Test dispatch order, lease expiry, retry exhaustion, review idempotency, human reminders, calendar behavior, pause during/after a turn, resume from stopped state, and single-daemon operations with synthetic tasks.

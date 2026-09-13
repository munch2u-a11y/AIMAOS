# Public-Beta Deployment Guide

## 1. Prepare the host

Use a dedicated, non-administrator Windows account or unprivileged Linux account on a supported Python 3.11–3.13 system. Enable full-disk encryption, OS security updates, a host firewall, and encrypted backups. Install Ollama separately and keep its API off untrusted networks.

## 2. Install

Windows:

```powershell
.\install.cmd
ollama pull qwen3.5:4b
ollama pull qwen3.5:2b
# Optional prose-only research model:
ollama pull gemma3:4b
.\.venv\Scripts\python.exe doctor.py
```

Linux:

```bash
bash install.sh
ollama pull qwen3.5:4b
ollama pull qwen3.5:2b
# Optional prose-only research model:
ollama pull gemma3:4b
.venv/bin/python3 doctor.py
```

Direct dependency intent is recorded in `requirements.txt`; reproducible runtime versions are pinned in `requirements.lock`. Re-run the doctor after configuration or model changes.

For release validation, install the separate development lock before running pytest:

```text
Windows: .\.venv\Scripts\python.exe -m pip install -r requirements-dev.lock
Linux:   .venv/bin/python3 -m pip install -r requirements-dev.lock
```

## 3. Review configuration

Before first use, check `aimaos_config.yaml`:

- Leave `ui.host` on `127.0.0.1`.
- Leave `ui.allow_lan` and `ui.developer_mode` false.
- Add only required document directories to `storage.allowed_roots`.
- Disable `ui.allow_native_open` when browser users are not physically using the AIMAOS host.
- Confirm all network, mutation, shell, and document-delegation security flags remain false.
- Confirm email is `READ_ONLY` with no approved recipients.
- Leave `workflow.direct_communications` false so communication work remains an attorney-owned reminder.
- Review `workflow.stale_task_hours` and the daily Agenda with the office's actual escalation policy.
- Select models that are actually installed and support tool calls where needed.

## 4. Start and smoke-test

```text
Windows: .\.venv\Scripts\python.exe aimaos_ui.py --no-browser
Linux:   .venv/bin/python3 aimaos_ui.py --no-browser
```

From the same machine, open `http://127.0.0.1:8080`. Confirm that:

1. The header eventually reports the office service as ready.
2. “Pause Agents” finishes the current turn and reaches paused; “Resume Agents” returns to ready without starting a duplicate daemon.
3. A synthetic text file can be imported into a synthetic matter.
4. The intake appears as a background job and exposes an honest completed or failed state.
5. The file can be downloaded and no absolute filesystem path appears in browser responses.
6. A generated draft displays the human-review notice.
7. “Refresh blockers” produces an idempotent Agenda, and a synthetic client-update task can be snoozed and completed without sending a message.
8. A synthetic DOCX or PDF can be reviewed in the dashboard, a line note creates `AIMAOS_REVIEW_NOTES.md`, and “Send open notes to agent” creates only one correction task.

Delete the synthetic matter data after testing according to your retention process.

## 5. Optional remote access

Remote access is for administrators who can operate a TLS reverse proxy. Keep AIMAOS on loopback and set a random token in the service environment:

```bash
export AIMAOS_UI_TOKEN="replace-with-at-least-32-random-bytes"
.venv/bin/python3 aimaos_ui.py --host 127.0.0.1 --no-browser
```

On Windows PowerShell, use `$env:AIMAOS_UI_TOKEN = "replace-with-at-least-32-random-bytes"` and launch with `.\.venv\Scripts\python.exe aimaos_ui.py --host 127.0.0.1 --no-browser`.

Terminate HTTPS and user authentication at a reverse proxy on the same host, then proxy to `127.0.0.1:8080`. Preserve the original `Host` header. Apply rate limits and network access control. Never expose port 8080 publicly or transmit the token over HTTP.

## 6. Operations

- Run `doctor.py` after upgrades and before support handoff.
- Monitor `comms/daemon_status.json`, job failures in the Home queue, disk space, and Ollama health.
- Review the Agenda at the start of each workday; its prioritization assists staff but does not establish or calculate legal deadlines.
- Stop AIMAOS before a consistent backup of runtime work and `comms/`.
- Test restore procedures with synthetic data.
- Review template provenance and official form revisions on a defined schedule.
- Upgrade from a reviewed commit and retain a rollback copy of application code and compatible data.

## 7. Public repository release gate

Before publishing a release, inspect `git ls-files`, embedded document metadata, commit-author metadata, and all reachable Git history. `.gitignore` does not remove data committed in an older revision. Do not publish generated agent workspaces, `comms/`, matter files, review sidecars, memories, credentials, local agent instructions, or absolute local paths. If an older public commit contains private/runtime data, use a coordinated history rewrite and credential rotation rather than a normal deletion commit.

## 8. Rollback

Stop the service, preserve runtime data, restore the previous reviewed application checkout, recreate its virtual environment from its pinned requirements, and start with `--no-browser`. Do not downgrade or overwrite the SQLite database without a tested migration or backup.

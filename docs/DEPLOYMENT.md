# Public-Beta Deployment Guide

## 1. Prepare the host

Use a dedicated, unprivileged Linux account on a supported Python 3.11–3.13 system. Enable full-disk encryption, OS security updates, a host firewall, and encrypted backups. Install Ollama separately and keep its API off untrusted networks.

## 2. Install

```bash
bash install.sh
ollama pull qwen3.5:4b
ollama pull qwen3.5:0.8b
.venv/bin/python3 doctor.py
```

Dependency versions are pinned in `requirements.txt`. Re-run the doctor after configuration or model changes.

## 3. Review configuration

Before first use, check `aimaos_config.yaml`:

- Leave `ui.host` on `127.0.0.1`.
- Leave `ui.allow_lan` and `ui.developer_mode` false.
- Add only required document directories to `storage.allowed_roots`.
- Confirm all network, mutation, shell, and document-delegation security flags remain false.
- Confirm email is `READ_ONLY` with no approved recipients.
- Select models that are actually installed and support tool calls where needed.

## 4. Start and smoke-test

```bash
.venv/bin/python3 aimaos_ui.py --no-browser
```

From the same machine, open `http://127.0.0.1:8080`. Confirm that:

1. The header eventually reports the office service as ready.
2. A synthetic text file can be imported into a synthetic matter.
3. The intake appears as a background job and exposes an honest completed or failed state.
4. The file can be downloaded and no absolute filesystem path appears in browser responses.
5. A generated draft displays the human-review notice.

Delete the synthetic matter data after testing according to your retention process.

## 5. Optional remote access

Remote access is for administrators who can operate a TLS reverse proxy. Keep AIMAOS on loopback and set a random token in the service environment:

```bash
export AIMAOS_UI_TOKEN="replace-with-at-least-32-random-bytes"
.venv/bin/python3 aimaos_ui.py --host 127.0.0.1 --no-browser
```

Terminate HTTPS and user authentication at a reverse proxy on the same host, then proxy to `127.0.0.1:8080`. Preserve the original `Host` header. Apply rate limits and network access control. Never expose port 8080 publicly or transmit the token over HTTP.

## 6. Operations

- Run `doctor.py` after upgrades and before support handoff.
- Monitor `comms/daemon_status.json`, job failures in the Home queue, disk space, and Ollama health.
- Stop AIMAOS before a consistent backup of runtime work and `comms/`.
- Test restore procedures with synthetic data.
- Review template provenance and official form revisions on a defined schedule.
- Upgrade from a reviewed commit and retain a rollback copy of application code and compatible data.

## 7. Rollback

Stop the service, preserve runtime data, restore the previous reviewed application checkout, recreate its virtual environment from its pinned requirements, and start with `--no-browser`. Do not downgrade or overwrite the SQLite database without a tested migration or backup.

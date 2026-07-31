# AIMAOS Public Beta

AIMAOS is a local-first office workflow copilot for organizing matter files, creating document drafts, routing background work, and querying a small roster of specialist agents through local models.

This is a public beta, not a replacement for Microsoft 365, Google Workspace, a practice-management system, or professional judgment. Generated documents and research are drafts that require human review.

## What the beta includes

- A task-oriented browser interface for Home, Matters, Create, Assistant, and Settings.
- Matter-scoped file intake, living summaries, safe downloads, and optional native opening.
- Template-driven DOCX generation with explicit draft and provenance warnings.
- Persistent background-job state, daemon heartbeat reporting, and failure visibility.
- Local Ollama inference with configurable models.
- Default-deny external actions, developer tools, shell tools, and document-triggered delegation.
- Approved storage roots, filename/path validation, CSRF protection, a restrictive content-security policy, and privacy-aware logs.

## Supported beta environment

The certified target for this beta is a modern Linux desktop with Python 3.11–3.13. macOS and Windows support is not yet certified. A local [Ollama](https://ollama.com/) service is the default model backend; downloading dependencies and models requires internet access, but routine operation can remain local afterward.

## Install and run

```bash
git clone <repository-url> AIMAOS
cd AIMAOS
bash install.sh
ollama pull qwen3.5:4b
ollama pull qwen3.5:0.8b
./Launch\ AIMAOS.sh
```

The setup step materializes runtime agent workspaces from `starter_packs/`. Open `http://localhost:8080` if a browser does not open automatically.

For a manual install:

```bash
python3 -m venv .venv
.venv/bin/python3 -m pip install -r requirements.lock
.venv/bin/python3 doctor.py
.venv/bin/python3 setup.py
.venv/bin/python3 aimaos_ui.py
```

## Before inviting beta users

Run the deployment check and release tests:

```bash
.venv/bin/python3 doctor.py
.venv/bin/python3 -m pytest
node --check ui/static/app.js
```

Then work through [the deployment guide](docs/DEPLOYMENT.md) and [public-beta checklist](docs/PUBLIC_BETA_CHECKLIST.md). Keep the dashboard on loopback unless it is protected by an authenticated TLS reverse proxy.

## Safety model

Public-beta defaults are intentionally conservative:

- `ui.host` is `127.0.0.1` and LAN binding is disabled.
- Network tools, external mutations, and email sends are disabled.
- Shell-backed and self-modifying agent tools require developer mode and an additional opt-in.
- Destructive and source-modifying maintenance tools are disabled in the beta configuration.
- Document content cannot autonomously create agent tasks.
- Raw tool output and raw task memory are not injected into future prompts by default.
- Agents can read only the application tree and storage roots explicitly listed in `storage.allowed_roots`.

See [SECURITY.md](SECURITY.md) and [PRIVACY.md](PRIVACY.md) before changing these settings.

## Data and backups

Runtime work is stored locally under generated `*-AI/workspace/` directories and `comms/`; these paths are excluded from git. The authoritative matter and job index is SQLite in `comms/office_database.sqlite`, while a compatibility JSON board remains during the beta.

Stop AIMAOS before copying these directories for backup. Never commit runtime folders, credentials, client documents, or model logs.

## Known beta limitations

- Bundled form metadata is incomplete; the UI marks those templates for source and revision verification.
- There is no multi-user permission model. LAN access is an administrator-managed deployment option, not a consumer toggle.
- Malware scanning, encrypted-at-rest storage, automatic upgrades, signed installers, and crash telemetry are not included.
- The legacy JSON office board still exists for agent compatibility alongside SQLite.
- Local models can hallucinate, misclassify files, or report incomplete work. Artifact and status checks reduce this risk but do not remove it.

## Development and tests

Fast, isolated release tests live in `tests/unit/` and are the default pytest target. Older benchmark scripts in `tests/` can invoke real models or mutate live runtime state; read [tests/README.md](tests/README.md) before running them.

```bash
.venv/bin/python3 -m pip install -r requirements-dev.lock
.venv/bin/python3 -m pytest
```

## Legal and professional-use notice

AIMAOS is software, not legal, tax, medical, or financial advice. Verify every field, citation, deadline, jurisdiction, official form revision, and recipient before relying on or sending output.

Licensed under the [Apache License 2.0](LICENSE). See [NOTICE](NOTICE).

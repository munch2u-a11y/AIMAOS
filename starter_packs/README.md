# AIMAOS Starter Packs & Profession Customization Architecture

A **starter pack** is the profession-specific content for the office roster (defined by job roles: Document Producer, Digital Librarian, Office Manager, Legal Researcher, DevOps Engineer, Security Gateway, Agent Maker). The shared kernel (`core/` at repo root — SQLite database core, bus, office board, LLM client, delegation pipeline, and vendored mRAG) and each agent's slot behavior are pack-independent. What varies per profession is each agent's `capabilities.yaml` (which tools it has, seed beliefs about how to use them), `tools/` implementations, and domain data assets (court-form `templates/`, for example).

`setup.py --pack <name>` materializes a pack into live `<Agent>-AI/` directories at the repo root. These directories are gitignored (see `.gitignore`) because they are generated outputs. The pack folders under `starter_packs/` are the actual tracked source of truth.

---

## 📁 Starter Pack Format & Structure

Each pack is structured as `starter_packs/<pack_name>/<Agent>-AI/`, mirroring a live agent directory minus `workspace/` (belief store + generated output — pure runtime state, never part of a pack):

```
starter_packs/<pack_name>/
├── Alix-AI/                  # Document Producer & Keeper (Jinja2, PDF, TOC)
│   └── templates/            # Clean template library
├── Kai-AI/                   # Digital Librarian & Archiver (Drive scanner, dedup)
├── Marley-AI/                # Office Manager & Priority Scheduler
├── Quinn-AI/                 # Legal & Statutory Research Intelligence
├── Zoe-AI/                   # DevOps Maintenance & Synthesizer
├── Finn-AI/                  # Security Officer & Comms Gateway
└── Rae-AI/                   # Agent Maker & Workspace Cloner
```

At minimum: `capabilities.yaml`, `config.yaml`, `core/agent.py` (the agent's slot class, e.g. `AlixAgent` subclassing `core.office_agent.OfficeAgent`), and `tools/*.py`.

`setup.py`'s `materialize_pack()` copies each `<Agent>-AI/` subtree from the chosen pack into the live location, then ensures `workspace/.memory/` exists (empty — the agent grows its own private mRAG belief store from there). It is non-destructive by default: an agent directory that already exists is left alone unless `--force` is passed, so switching packs or re-running setup never silently wipes an office's accumulated identity.

---

## 🏛️ Integrated Office Capabilities & Extensions

### 1. Relational SQLite Database Core (`core/db/office_sqlite.py`)
- Tracks `cases`, `tasks`, `templates`, and dashboard jobs in `comms/office_database.sqlite`.
- Matter tools maintain the human-readable `CLIENT_FILE.md`; SQLite does not independently author that summary.

### 2. External Drive Ingestion Pipeline (`shared_tools/ingest_ssd_drive.py`)
- Scans external drives (a drive or folder path you pass in), classifies documents vs templates, provisions case directories under `Alix-AI/workspace/output/`, and instantiates dedicated `CaseAgent` managers.

### 3. Cross-Case Category Skill Sharing (`core/db/category_skills.py`)
- Maintains shared category skills at `comms/category_skills/<category>.json`.
- `CaseAgent` managers working in the same practice area (e.g. `name_change`, `estate_planning`, `probate`, `guardianship`, `family`) inherit category procedural knowledge without cluttering individual client files.

### 4. Notes and optional audio utilities
- The workstation can attach typed operator notes to a selected matter.
- Shared local/remote speech utilities exist, but the public starter pack does not currently expose an end-to-end microphone transcription workflow. Audio uploads should not be described as transcribed until that feature is implemented and tested.

### 5. Software-Enforced Email Security Gateway (`Alix-AI/business/watchers/email_connector.py`)
- Configurable via `aimaos_config.yaml`: `READ_ONLY` (default, blocks outbound sending) or `WHITELIST_ONLY` (approved recipients only), in addition to central network/external-mutation gates.

---

## 📜 Role-Agnostic Starter Roster Matrix

| Functional Job Title | Starter Name Preset | Core Role & Responsibilities |
| :--- | :--- | :--- |
| **Document Producer & Keeper** | `Alix` (Default) | Jinja2 Word template rendering, TOC OpenXML injection, PDF compilation, template cataloger (`catalog_templates.py`). |
| **Digital Librarian & Archiver** | `Kai` (Default) | Drive ingestion scanner (`drive_ingestion.py`), client record deduplication, task execution trace archival. |
| **Office Manager & Scheduler** | `Marley` (Default) | Autonomous office daemon pulse loop (`office_daemon.py`), priority turn scheduling (`CRITICAL`, `HIGH`, `NORMAL`, `BACKGROUND`), load balancing. |
| **Legal & Statutory Researcher** | `Quinn` (Default) | Statutory legal research, Florida Rules of Civil & Family Procedure, memorandum writing. |
| **DevOps Engineer & Synthesizer** | `Zoe` (Default) | Workspace diagnostics and developer-gated tool/agent engineering. |
| **Security Officer & Comms Gateway** | `Finn` (Default) | Incoming triage, office status, and software-enforced outbound policy (`READ_ONLY`, `WHITELIST_ONLY`). |
| **Agent Maker & Cloner** | `Rae` (Default) | Workspace cloner (`clone_agent.py`), fully integrating new clones into main config, IPC bus queues, and Office Board. |
| **Dedicated Case Manager** | `CaseAgent` (Dynamic) | Per-matter mini-agent. Drafts `CLIENT_FILE.md` summaries, required-document checklists, and next steps; recorded dates still require staff verification. |

All starter-pack capabilities remain subject to `core/security.py`. Network, external mutation, shell, developer, and document-triggered delegation paths are disabled in the public-beta defaults even when a module exists in source.

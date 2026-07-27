# AIMAOS - AI Multi-Agent Office Suite Operating System

> **Autonomous, 100% Offline, Multi-Agent Enterprise Office Suite & Document Production Engine**  
> Inspired by Helix AGI Architecture. Optimized for local LLMs (2B–8B parameter models).

---

## ⚡ System Overview

**AIMAOS** (*AI Multi-Agent Office Suite*) is a self-contained, offline multi-agent operating system designed for law firms, document production centers, and enterprise record management. It orchestrates seven specialized mini-agents operating in isolated workspaces, communicating asynchronously through a file-queue Inter-Process Communication (IPC) bus and a central Office Board bulletin system.

---

## 🤖 Active Agent Company Roster

| Agent Name | Specialized Role | Default LLM Model | Primary Responsibilities |
| :--- | :--- | :--- | :--- |
| **Alix-AI** | Document Production | `gemma2:9b` / `granite3.1` | Jinja2 Word template rendering, TOC injection, PDF compilation, client output dispatch |
| **Kai-AI** | Digital Librarian | `llama3.1:8b` | Client record deduplication, cataloging, and task execution log archival |
| **Marley-AI** | Office Manager | `qwen2.5:7b` | Turn priority scheduling, CPU/GPU load balancing, and calendar event management |
| **Quinn-AI** | Researcher | `mistral:7b` | Statutory legal research, case law analysis, and procedural briefing reports |
| **Zoe-AI** | DevOps Engineer | `llama3.1:8b` | System diagnostics, task trace analysis, and adaptive improvement report synthesis |
| **Finn-AI** | Security Officer | `llama3:latest` | Incoming message triage, sender permission checks, chat gateway, outbound channel commandering |
| **Rae-AI** | Agent Maker | `llama3.1:8b` | Dynamic mini-agent workspace cloning engine (instantiating new agent instances) |

---

## 🚀 Key Features

* **Helix-Style Ultra-Minimal System Prompts**: System prompts are condensed to identity + top mRAG belief. Context and procedural rules are injected dynamically per turn via mRAG.
* **Single-Thought Turn Execution Loop**: Each turn represents a single discrete thought or task execution cycle, preventing CPU/GPU hardware throttling.
* **Self-Contained All-in-One Dashboard (`aimaos_ui.html`)**: Served locally on `http://localhost:8080` with a 5-tab glassmorphism UI:
  1. **🏢 Office Dashboard**: Visual Kanban table and live activity stream ticker.
  2. **💬 Direct Messenger (Finn)**: Chat interface for asking questions or posting tasks.
  3. **📄 Document Studio (Alix)**: Court form template selector and context renderer.
  4. **📊 System Reports**: Operational diagnostics and legal research briefs.
  5. **🤖 Agent Cloner Studio (Rae)**: Instant agent workspace cloner.
* **Multi-County Legal Document Production**: Native support for Florida Court forms (Adult Name Change, Minor Child Guardianship, Simplified Dissolution of Marriage, Financial Affidavits, Child Support Worksheets).
* **Multi-Channel Dispatcher**: Outbound client legal packages emailed directly to `helix.agi.system@gmail.com` via `helix.agi.system@gmail.com`.

---

## 📁 System Directory Layout

```
/path/to/AIMAOS/
├── Alix-AI/                  # Document Production Agent Workspace
├── Kai-AI/                   # Digital Librarian & Task Archiver Workspace
├── Marley-AI/                # Office Manager & Priority Scheduler Workspace
├── Quinn-AI/                 # Research & Legal Intelligence Workspace
├── Zoe-AI/                   # DevOps Maintenance Engineer Workspace
├── Finn-AI/                  # Security Officer & Comms Gateway Workspace
├── Rae-AI/                   # Agent Maker & Workflow Cloner Workspace
├── comms/                    # Central IPC Communication Bus & Office Board
│   ├── office_board.json     # Atomic Bulletin Board State
│   └── task_logs/            # Kai Archived Task Traces
├── ui/                       # Embedded Web Server & Static Files
│   ├── aimaos_ui.html        # 5-Tab Glassmorphism Dashboard
│   └── static/index.html     # Web UI Layout
├── System Technical Documents/# Full Technical Audit Suite & Architecture Docs
├── aimaos_ui.py              # UI Engine Server Launcher
├── main.py                   # System CLI Entrypoint
├── setup.py / setup.sh       # Multi-Model Setup Wizard
├── Launch AIMAOS.sh          # One-Click Executable Shell Launcher
└── tests/                    # End-to-End Integration Test Suites
```

---

## ⚙️ Quick Start Guide

### 1. Run Setup Wizard & Multi-Model Configurator
```bash
./setup.sh
# or
python3 setup.py
```

### 2. Launch All-in-One Dashboard & Browser
```bash
"./Launch AIMAOS.sh"
# or
python3 main.py
```
*Access the Web Dashboard at:* **`http://localhost:8080`**

### 3. Run Integration Test Suite
```bash
/path/to/user/Alix-AI/.venv/bin/python3 tests/test_multi_county_email_dispatch.py
/path/to/user/Alix-AI/.venv/bin/python3 tests/test_all_in_one_ui.py
```

---

## 🛡️ License & Safety

* **Local State Isolation**: 100% offline, private local execution. No paid API credits consumed.
* **Credentials Security**: Credentials managed safely via `~/.config/helix/credentials.env` and `~/.env`.

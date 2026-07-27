# Technical Audit: Rae-AI (Agent Maker & Workflow Cloner Engine)

## 1. Agent Overview
- **Workspace**: `/path/to/AIMAOS/Rae-AI`
- **Primary Function**: Dynamic workspace instantiation and mini-agent cloning.

---

## 2. Core Modules & Code Citations

### 2.1. Agent Cloner Engine (`tools/clone_agent.py`)
Dynamically creates a new specialized mini-agent workspace at `/path/to/AIMAOS/<AgentName>-AI` with isolated config (`config.yaml`), IPC bus (`core/comms/bus.py`), agent orchestrator (`core/agent.py`), and memory directories.

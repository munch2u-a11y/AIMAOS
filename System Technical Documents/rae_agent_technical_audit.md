# Technical Audit: Rae-AI (Agent Maker & Workflow Cloner Engine)

## 1. Agent Overview
- **Workspace**: `<office root>/Rae-AI`
- **Primary Function**: Dynamic mini-agent workspace creation, agent persona cloning, and custom tool binding on demand.
- **Model**: `qwen3.5:2b` (configured in `aimaos_config.yaml`).

---

## 2. Core Modules & Code Citations

### 2.1. Workspace Cloner Engine (`tools/clone_agent.py`)
Dynamically instantiates new specialized mini-agent workspaces at `<office root>/<AgentName>-AI` with isolated configs (`config.yaml`), IPC bus (`core/comms/bus.py`), mRAG belief stores (`workspace/.memory/mrag_data/`), and custom tool directories.

```python
def execute(agent_name, role):
    # 1. Provisions <office root>/<AgentName>-AI workspace directory
    # 2. Creates isolated config.yaml, capabilities.yaml, and IPC inbox/outbox queues
    # 3. Writes core/agent.py as a full OfficeAgent subclass (delegation-enabled)
    # 4. Seeds the private mRAG identity store via the BeliefStore API
    # 5. Registers the agent in aimaos_config.yaml and on the Office Board
```

### 2.2. Specialist Tooling (delegated to Zoe)
The cloner provisions an empty `tools/` directory. Equipping a new agent is
Zoe's `design_tool_subagent` job: it writes the tool module, registers it under
a capability domain in the clone's `capabilities.yaml`, and seeds the first
beliefs about how that tool behaves. This keeps agent creation and tool
engineering as separate, independently testable steps.

---

## 3. Capabilities & Capabilities Schema
- **Domains**: `file_research`, `agent_making`
- **Capabilities Config**: `Rae-AI/capabilities.yaml`
- **Registered Tools**:
  - `clone_agent`: Instantiates a new mini-agent workspace with its own config, capabilities, belief store, and IPC queues.

New clones are born with the universal `file_research` capability only; Zoe's
`design_tool_subagent` then equips them with the specialist tools their role needs.

# Technical Audit: DevOps Engineer & Synthesizer (Zoe Preset)

## 1. Agent Overview
- **Workspace**: `<office root>/Zoe-AI`
- **Primary Function**: System diagnostics, task execution trace analysis, performance bottleneck detection, and Hermes-style operational improvement report synthesis.
- **Model**: `qwen3.5:2b` (configured in `aimaos_config.yaml`).

---

## 2. Core Modules & Code Citations

### 2.1. Hermes Workflow Synthesizer (`core/workflow_synthesizer.py`)
Operates during background turns scheduled by Marley. Reads Kai's archived task traces (`comms/task_logs/`), analyzes execution bottlenecks, tool failure rates, and token budgets, and generates system improvement reports.

```python
class ZoeWorkflowSynthesizer:
    def synthesize_improvement_report(self):
        # 1. Inspects archived execution traces in <office root>/comms/task_logs/
        # 2. Computes tool call success rates, average turn latency, and error frequencies
        # 3. Formats Hermes diagnostic report to Zoe-AI/workspace/diagnostics/diagnostic_report_<timestamp>.md
```

### 2.2. Self-Healing & Capability Recommendation Engine
- Recommends skill refinements and prompt parameter adjustments based on historical execution logs.
- Triggers Rae Agent Maker requests if specialized workload bottlenecks emerge.

---

## 3. Capabilities & Capabilities Schema
- **Domains**: `file_research`, `diagnostics`, `tool_engineering`, `agent_engineering`
- **Capabilities Config**: `Zoe-AI/capabilities.yaml`
- **Registered Tools**:
  - `system_diagnostics`: Audits every agent workspace (config present, script counts, IPC bus) and computes a health percentage from the actual check results.
  - `design_tool_subagent`: Designs a new tool subagent for any agent — writes the module, registers it under a capability domain, and seeds its first how-to beliefs.
  - `clone_agent`: Instantiates a new agent workspace (shared with Rae).

The improvement report itself is produced by `core/workflow_synthesizer.py`, which
Marley's daemon calls directly on background turns rather than through a registered tool.

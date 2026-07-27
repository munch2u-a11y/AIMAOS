# Technical Audit: Zoe-AI (DevOps Maintenance Engineer & Synthesizer)

## 1. Agent Overview
- **Workspace**: `/path/to/AIMAOS/Zoe-AI`
- **Primary Function**: System diagnostics, task execution trace analysis, and Hermes-style operational improvement report synthesis.

---

## 2. Core Modules & Code Citations

### 2.1. Hermes Workflow Synthesizer (`core/workflow_synthesizer.py`)
Analyzes Kai's archived task execution traces and writes structured system improvement reports to `Zoe-AI/workspace/diagnostics/hermes_report_YYYYMMDD_HHMMSS.md`.

```python
class ZoeWorkflowSynthesizer:
    def synthesize_improvement_report(self):
        # Reads logs from /path/to/AIMAOS/comms/task_logs/
        # Synthesizes operational bottlenecks, error rates, and skill optimizations
```

# Technical Audit: Marley-AI (Office Manager & Priority Scheduler)

## 1. Agent Overview
- **Workspace**: `/path/to/AIMAOS/Marley-AI`
- **Primary Function**: Turn priority scheduling, CPU/GPU load balancing, turn dispatching, and calendar event management.

---

## 2. Core Modules & Code Citations

### 2.1. Marley Dispatch Orchestrator (`core/orchestrator.py`)
Prevents local hardware (CPU/GPU) bottlenecks by maintaining an ongoing stream of agent turns, ensuring only one high-compute task runs at a time.

```python
class MarleyOrchestrator:
    def dispatch_next_turn(self):
        # Priority Weights: CRITICAL (0), HIGH (1), NORMAL (2), BACKGROUND (3)
        # Prioritizes Alix (Docs) & Quinn (Research), shifts Zoe (Maintenance) to background.
```

### 2.2. Calendar & Schedule Manager (`tools/manage_schedule.py`)
- Manages office deadlines, court hearing dates, and task completion milestones stored in `workspace/schedule.json`.

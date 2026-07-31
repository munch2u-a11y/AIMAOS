# Technical Audit: Office Manager & Priority Scheduler (Marley Preset)

## 1. Agent Overview
- **Workspace**: `<office root>/Marley-AI`
- **Primary Function**: Autonomous office daemon loop management, turn priority scheduling, CPU/GPU load balancing, task lease hygiene, and calendar event tracking.
- **Model**: `qwen3.5:2b` (configured in `aimaos_config.yaml`).

---

## 2. Core Modules & Code Citations

### 2.1. Marley Office Daemon Loop (`core/office_daemon.py`)
Marley operates as the main autonomous daemon pulse driving the entire AIMAOS office suite single-thought turn execution loop.

```python
class OfficeDaemon:
    def pulse(self):
        # 1. Audit Office Board hygiene (lease timeouts, requeue failed tasks)
        # 2. Check agent inbox queues for inter-agent IPC dispatches
        # 3. Schedule next highest priority turn from Office Board / SQLite database
        # 4. Execute single-thought LLM turn for assigned roster agent
        # 5. Trigger rotating background identity reflections
```

### 2.2. Priority Dispatch & Load Balancer (`core/orchestrator.py`)
Prevents local hardware (CPU/GPU) bottlenecks by maintaining a single-thought turn sequence, ensuring high-value user workloads take immediate precedence over background maintenance.

```python
class MarleyOrchestrator:
    def dispatch_next_turn(self):
        # Priority Weights:
        #   CRITICAL (10) - Emergency client dispatches
        #   HIGH (7)     - Alix document filings & Quinn statutory research
        #   NORMAL (5)   - Kai librarian cataloging & drive ingestion
        #   BACKGROUND (1)- Zoe diagnostic reports & maintenance
```

### 2.3. Task Lease Hygiene & Requeue Engine
- Audits stale tasks where `lease_expires_at < current_time`.
- Requeues interrupted tasks up to `max_task_retries: 2`.
- Prevents deadlocks if an agent process exits unexpectedly.

### 2.4. Calendar & Schedule Manager (`tools/manage_schedule.py`)
- Manages office deadlines, court hearing dates, and task completion milestones stored in `workspace/calendar/events.json` and synced to the relational SQLite database.

---

## 3. Capabilities & Capabilities Schema
- **Domains**: `file_research`, `scheduling`, `office_utilities`
- **Capabilities Config**: `Marley-AI/capabilities.yaml`
- **Registered Tools**:
  - `manage_schedule`: Adds, updates, or lists calendared hearing dates and filing deadlines.
  - `google_calendar`: Optional external calendar sync (inactive until credentials are configured).
  - `calculator`, `unit_converter`, `timezone_convert`: General office utilities.

Task-lease hygiene is not a registered tool — it runs directly in the daemon's
pulse (`core/office_daemon.py`: `requeue_expired_and_failed`), which requeues
leases past `office.task_lease_sec` and abandons tasks that exhaust
`office.max_task_retries`.

# Technical Audit: AIMAOS Inter-Agent Subsystems, Storage, & Category Knowledge

## 1. Overview
The inter-agent communication layer, relational storage core, and cross-case practice knowledge sharing architecture of **AIMAOS** consists of decoupled, 100% offline components:
1. **Relational SQLite Kernel** ([`core/db/office_sqlite.py`](../core/db/office_sqlite.py))
2. **Cross-Case Category Skill Repository** ([`core/db/category_skills.py`](../core/db/category_skills.py))
3. **File-Queue IPC Bus** ([`core/comms/bus.py`](../core/comms/bus.py))
4. **Central Office Board & Activity Ticker** ([`core/comms/office_board.py`](../core/comms/office_board.py))
5. **Dedicated Case Managers** ([`core/case_agent.py`](../core/case_agent.py))
6. **Hardware-Enforced Security Gateway** ([`Alix-AI/business/watchers/email_connector.py`](../Alix-AI/business/watchers/email_connector.py))

---

## 2. Storage, Schemas, & Cross-Case Knowledge Inheritance

### 2.1. Relational Database Schema (`comms/office_database.sqlite`)
- **`cases`**: `(client_slug PRIMARY KEY, client_name, matter_type, category, status, case_number, opened_at, updated_at, path)`
- **`tasks`**: `(task_id PRIMARY KEY, title, description, assigned_agent, priority, priority_weight, status, created_at, updated_at, lease_expires_at)`
- **`templates`**: `(template_id PRIMARY KEY, filename, category, rel_path, size_bytes, modified_at)`

### 2.2. Category Skill Repository (`core/db/category_skills.py`)
Maintains practice-area procedural knowledge repositories at `<office root>/comms/category_skills/<category_slug>.json`.
- **Isolation Guarantee**: Confidential client data remains strictly inside that client's isolated case directory (`.case_agent/mrag_data/`).
- **Inheritance Mechanism**: Whenever a new `CaseAgent` is instantiated for a given category (e.g., `name_change`, `estate_planning`, `probate`), it automatically loads and pre-seeds those category skills into its initial mRAG store.

### 2.3. IPC Envelope Schema & Message Flow

```json
{
  "id": "msg_20260727_190926_809708",
  "sender": "Alix",
  "recipient": "Kai",
  "action": "check_duplicates",
  "payload": { "query_text": "Alex Sample Name Change" },
  "timestamp": "2026-07-27T19:09:26.809708",
  "status": "pending"
}
```

1. **Dispatch**: Messages are written to `<office root>/comms/<Recipient>/inbox/<msg_id>.json`.
2. **Consumption**: The recipient reads pending messages and renames processed files to `.read`.
3. **Reply**: The recipient writes a reply envelope to `<office root>/comms/<Sender>/inbox/reply_<msg_id>.json`.

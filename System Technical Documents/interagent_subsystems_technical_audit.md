# Technical Audit: AIMAOS Inter-Agent Subsystems & IPC Architecture

## 1. Overview
The inter-agent communication layer of **AIMAOS** consists of four decoupled, 100% offline components:
1. **File-Queue IPC Bus** ([`core/comms/bus.py`](file:///path/to/AIMAOS/Alix-AI/core/comms/bus.py))
2. **Central Office Board & Activity Ticker** ([`core/comms/office_board.py`](file:///path/to/AIMAOS/Alix-AI/core/comms/office_board.py))
3. **Channel Commandering Subsystem** ([`Finn-AI/tools/commandeer_channel.py`](file:///path/to/AIMAOS/Finn-AI/tools/commandeer_channel.py))
4. **Email & Package Dispatcher** ([`Alix-AI/core/watchers/email_connector.py`](file:///path/to/AIMAOS/Alix-AI/core/watchers/email_connector.py))

---

## 2. Envelope Schema & Message Flow

```json
{
  "id": "msg_20260727_190926_809708",
  "sender": "Alix",
  "recipient": "Kai",
  "action": "check_duplicates",
  "payload": { "query_text": "Alexander Montgomery Name Change" },
  "timestamp": "2026-07-27T19:09:26.809708",
  "status": "pending"
}
```

1. **Dispatch**: Messages are written to `/path/to/AIMAOS/comms/<Recipient>/inbox/<msg_id>.json`.
2. **Consumption**: The recipient reads pending messages and renames processed files to `.read`.
3. **Reply**: The recipient writes a reply envelope to `/path/to/AIMAOS/comms/<Sender>/inbox/reply_<msg_id>.json`.

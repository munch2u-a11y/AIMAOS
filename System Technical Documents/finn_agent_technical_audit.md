# Technical Audit: Finn-AI (Security Officer & Comms Gateway)

## 1. Agent Overview
- **Workspace**: `/path/to/AIMAOS/Finn-AI`
- **Primary Function**: Incoming message security triage, permission verification, chatbot user messaging, and peer agent channel commandering.

---

## 2. Core Modules & Code Citations

### 2.1. Incoming Security Triage Tool (`tools/triage_incoming.py`)
Inspects unsolicited incoming messages from Email, Web UI, Discord, or Telegram, verifies sender credentials (`VERIFIED` for allowed domains), extracts intent, and posts task items to the Office Board.

### 2.2. Gateway Channel Commandering Tool (`tools/commandeer_channel.py`)
Enables active turn agents (**Alix**, **Quinn**, **Marley**) to commandeer Finn's communication gateway to send outbound email packages with attached court forms to clients (`helix.agi.system@gmail.com`).

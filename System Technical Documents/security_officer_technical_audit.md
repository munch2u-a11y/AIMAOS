# Technical Audit: Security Officer & Comms Gateway (Finn Preset)

## 1. Agent Overview
- **Workspace**: `<office root>/Finn-AI`
- **Primary Function**: Incoming communication security triage, sender permission verification, client package output gateway, hardware email security policy enforcement, and Voice Scribe audio dictation transcription.
- **Model**: `qwen3.5:2b` (configured in `aimaos_config.yaml`).

---

## 2. Core Modules & Code Citations

### 2.1. Hardware-Enforced Email Security Gateway (`Alix-AI/business/watchers/email_connector.py`)
Enforces strict outbound security modes configured in `aimaos_config.yaml`:
- **`READ_ONLY` Mode (Default)**: Hard-blocks all outbound email attempts at the code level, raising a `SecurityPolicyException`.
- **`WHITELIST_ONLY` Mode**: Restricts outbound sending strictly to approved email addresses in `approved_recipients`.

```python
def check_outbound_policy(self, recipient):
    if self.security_mode == "READ_ONLY":
        raise SecurityPolicyException("SECURITY POLICY BLOCKED: READ_ONLY mode is active. Outbound emails are disabled system-wide.")
    if self.security_mode == "WHITELIST_ONLY":
        if recipient.lower() not in [r.lower() for r in self.approved_recipients]:
            raise SecurityPolicyException(f"SECURITY POLICY BLOCKED: Recipient '{recipient}' is not in approved whitelist.")
    return True
```

### 2.2. Voice Scribe & Audio Transcription Tool (`tools/transcribe_audio_note.py`)
Transcribes audio recordings (`.wav`, `.mp3`, `.m4a`, `.webm`) using local transcription models (`shared_tools/transcribe_audio.py`), identifies target client cases, and automatically attaches transcript summaries into `CLIENT_FILE.md`.

```python
def execute(audio_path, client_name=None):
    res = transcribe_audio_file(audio_path)
    transcript = res.get("transcript", "")
    # Updates target client CaseAgent record and CLIENT_FILE.md
```

### 2.3. Incoming Security Triage Engine (`tools/triage_incoming.py`)
Inspects unsolicited incoming communications from Email, Web UI, Discord, or Telegram. Verifies sender security status against allowed domain/email whitelists before posting tasks to the Office Board.

### 2.4. Gateway Channel Commandering Subsystem (`tools/commandeer_channel.py`)
Enables active roster turn agents (**Alix**, **Quinn**, **Marley**) to commandeer Finn's communication gateway to dispatch outbound email packages, subject to hardware policy verification.

---

## 3. Capabilities & Capabilities Schema
- **Domains**: `file_research`, `gateway`, `voice_scribe`
- **Capabilities Config**: `Finn-AI/capabilities.yaml`
- **Registered Tools**:
  - `triage_incoming`: Audits sender security and logs verified requests to the Office Board.
  - `commandeer_channel`: Dispatches client packages subject to hardware policy rules.
  - `transcribe_audio_note`: Transcribes audio dictation and syncs summaries to client case records.

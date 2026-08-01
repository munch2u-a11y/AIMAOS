# Technical Audit: Security and Communications Gateway (Finn Preset)

**Tracked source:** [`starter_packs/document_heavy/Finn-AI/`](../starter_packs/document_heavy/Finn-AI/)
**Live workspace after setup:** `<office root>/Finn-AI/`
**Configured model:** `qwen3.5:2b` in the checked-in example configuration.

## Role

Finn provides incoming-message classification, office-status inspection, and a policy-gated outbound communication wrapper. Security is ultimately enforced by deterministic code in `core/security.py` and the email connector, not by Finn's model judgment.

## Incoming triage

[`tools/triage_incoming.py`](../starter_packs/document_heavy/Finn-AI/tools/triage_incoming.py) parses the sender's actual domain, classifies simple research/scheduling/document intent, and posts a task to the Office Board. Its allowlist is a small code-level example, not a production identity proof. A sender marked “verified” by domain matching is not cryptographically authenticated.

Raw incoming text is untrusted and may contain prompt injection. It remains task data and must not override system/tool policy.

## Outbound gateway

[`tools/commandeer_channel.py`](../starter_packs/document_heavy/Finn-AI/tools/commandeer_channel.py) calls Alix's [`email_connector.py`](../starter_packs/document_heavy/Alix-AI/business/watchers/email_connector.py). The path has layered software controls:

1. central tool policy blocks network tools by default;
2. central policy separately blocks external mutations by default;
3. email mode defaults to `READ_ONLY` and can restrict recipients;
4. SMTP requires `AIMAOS_SMTP_SEND=1` and credentials;
5. results distinguish blocked, simulated, failed, and dispatched states;
6. a matter activity entry is written only for an actual dispatched result.

The workstation's public-beta workflow does not expose direct send as a normal task. Requests such as “update the client” become attorney/staff reminders.

## Office status

`check_office_status.py` reports board/agent state. It is an operational snapshot, not a health or security attestation.

## Audio status

Shared speech-to-text utilities exist, and the API can attach typed notes to a matter. The public starter pack does not currently include the former `transcribe_audio_note.py` wrapper, and the workstation does not offer direct microphone recording/transcription. Documentation must not advertise an integrated Voice Scribe until a complete, tested UI-to-local-transcriber flow exists.

## Limitations

- Domain allowlisting is not sender authentication.
- IMAP/SMTP, remote speech, Telegram, and similar credentials alter the privacy boundary.
- Email connector logs can contain message bodies and recipients in private runtime storage.
- Software flags can be changed by an administrator; “disabled by default” is not an immutable guarantee.
- The system has no multi-user approval identity or audit-grade signature.

## Verification

Test spoofed domains, unverified priority, default network denial, external-mutation denial, `READ_ONLY`, whitelist rejection, simulated mode, SMTP failure, truthful dispatch status, attachment path validation, and log privacy using synthetic addresses/content.

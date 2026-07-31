# Security Policy

## Public-beta boundary

AIMAOS is a single-operator, local-first application. Its default HTTP listener is loopback-only. It is not designed to be exposed directly to the internet and does not provide tenant isolation, user roles, account recovery, or an audit-grade identity system.

## Safe deployment defaults

- Keep `ui.host: 127.0.0.1` and `ui.allow_lan: false`.
- Keep `security.allow_network_tools`, `security.allow_external_mutations`, `security.allow_shell_tools`, and `security.allow_document_delegation` false.
- Keep `ui.developer_mode` false on consumer installations.
- Add only narrowly scoped directories to `storage.allowed_roots`; never add a whole home directory or filesystem root.
- Run the process as an unprivileged OS user with access only to required work data.
- Keep the application and its work directories off public file shares.

For remote access, place an authenticated TLS reverse proxy on the same host, keep AIMAOS bound to loopback, set a long random `AIMAOS_UI_TOKEN`, and forward that loopback service. Do not send a dashboard token over plain HTTP.

## Untrusted content

Documents, filenames, web results, messages, and retrieved memory are treated as untrusted data. Prompt text instructs agents not to follow embedded instructions, tool calls pass through a deterministic policy, document-triggered delegation is disabled, and paths are checked against approved roots. These controls reduce prompt-injection risk but cannot guarantee that a local model will behave correctly.

Review every generated artifact and every proposed external action. Do not enable outbound mutations until a separate human approval workflow is in place.

## Reporting a vulnerability

Do not include client files, secrets, absolute local paths, or model transcripts in a public issue. Use the repository owner's private security-reporting channel. Include the affected commit, reproduction steps using synthetic data, expected impact, and any suggested mitigation.

## Response expectations

This beta does not promise a formal response SLA. Confirmed critical issues should block further public-beta distribution until patched and regression-tested.

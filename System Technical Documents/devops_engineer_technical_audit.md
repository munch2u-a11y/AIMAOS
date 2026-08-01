# Technical Audit: Diagnostics and Tool Engineer (Zoe Preset)

**Tracked source:** [`starter_packs/document_heavy/Zoe-AI/`](../starter_packs/document_heavy/Zoe-AI/)
**Live workspace after setup:** `<office root>/Zoe-AI/`
**Configured model:** `qwen3.5:4b` in the checked-in example configuration.

## Role

Zoe provides local workspace diagnostics and developer-gated tool/agent engineering. The role supports maintenance; it is not an autonomous self-modifying or self-healing security mechanism.

## Implemented components

### Workspace diagnostics

[`tools/system_diagnostics.py`](../starter_packs/document_heavy/Zoe-AI/tools/system_diagnostics.py) checks whether expected live agent directories/configuration exist, counts Python files, and reports whether the IPC directory exists. Its percentage is a simple availability summary, not a security, correctness, model-health, or data-integrity certification.

### Tool engineering

[`tools/design_tool_subagent.py`](../starter_packs/document_heavy/Zoe-AI/tools/design_tool_subagent.py) can create a Python tool module, register it under a target agent's capability domain, and add seed beliefs. [`shared_tools/install_catalog_tool.py`](../shared_tools/install_catalog_tool.py) installs an implemented shared tool or a clearly marked scaffold.

Both operations are developer tools and are denied by default.

### Workflow synthesizer

[`core/workflow_synthesizer.py`](../starter_packs/document_heavy/Zoe-AI/core/workflow_synthesizer.py) can compute metrics from Office Board records and archived task traces and optionally ask Zoe's model for a narrative. It exists as a callable component but is not automatically invoked by the current daemon pulse. Documentation and UI must not imply that improvement reports continuously tune the office.

## Capability surface

- `diagnostics`: workspace check tool;
- `tool_engineering`: design, catalog, and installation tools;
- `agent_engineering`: clone helper;
- `file_research`: approved local file tools.

## Trust boundary

Tool generation is code generation. Before activation, a human should review imports, subprocess/network use, path handling, schema, output behavior, and policy classification. A healthy diagnostic count does not establish that a generated tool is safe.

## Known limitations

- No automatic patch deployment, rollback, or verification pipeline exists.
- Diagnostic checks do not inspect model output quality or matter correctness.
- Task-trace archival is not automatically wired into every daemon completion path.
- Developer-mode mutations affect the live workspace and need backup/migration planning.

## Verification

Run `doctor.py`, the unit suite, Python compilation, a synthetic diagnostic, and focused tests for every generated tool. Keep tool engineering disabled on consumer installations.

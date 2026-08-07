# AIMAOS Case Specialist

This local-only plugin exposes one shared `manage-case-specialist` Agent Skill to Codex and Claude Code. The skill adopts existing AIMAOS matters in place; it does not generate a new office-wide agent or move case data.

## Codex local installation

From the AIMAOS repository root:

```text
codex plugin marketplace add .
codex plugin add aimaos-case-specialist@aimaos-local
```

The marketplace definition is versioned at `.agents/plugins/marketplace.json`. This plugin is not submitted to a public marketplace.

## Claude Code local development

Start Claude Code with the plugin directory:

```text
claude --plugin-dir ./plugins/aimaos-case-specialist
```

Validate the package with:

```text
claude plugin validate --strict ./plugins/aimaos-case-specialist
```

No Claude marketplace publication is included in v1.

## Operations

Ask either runtime to use `manage-case-specialist` with an approved case folder or AIMAOS case identifier. The available operations are `initialize`, `refresh`, `status`, `audit`, and `dry-run`.

The AIMAOS adapter updates the working overview but never sends external communications or creates calendar events. Internal assignments require the existing `security.allow_document_delegation` setting to be explicitly enabled. Candidate dates become staff-verification tasks only.

# Product Beta Roadmap

This roadmap separates what AIMAOS needs for a responsible small public beta from features that belong in later product releases. The benchmark was refreshed on 2026-07-31 using vendors' official product and support material.

## Experience benchmark

Current office-AI products converge on a few useful interaction patterns:

- [Microsoft 365 Copilot](https://support.microsoft.com/en-us/microsoft-365-copilot/what-is-the-microsoft-365-copilot-app) presents one home for chat, files, search, content creation, and focused agents.
- [Google Workspace with Gemini](https://knowledge.workspace.google.com/admin/generative-ai/workspace-with-gemini/google-workspace-with-gemini) puts contextual assistance inside the applications where work already happens and gives administrators centrally managed data controls.
- [Notion Research Mode](https://www.notion.com/help/research-mode) exposes the sources used, lets the user narrow the source set, supports follow-up questions, and can save a result as a durable workspace artifact.
- [Zoho Workplace](https://www.zoho.com/workplace/help/ai-in-zoho-workplace.html) emphasizes an assistant embedded across mail, documents, files, meetings, and other daily tools rather than a separate chat destination.
- [ONLYOFFICE AI](https://www.onlyoffice.com/blog/2026/07/onlyoffice-made-friends-with-ai) combines inline document actions, reusable assistants, local Ollama support, provider choice, and opt-in AI processing.

AIMAOS should not imitate the breadth of these mature suites during beta. Its defensible product promise is narrower: a private, local-first office work queue that turns files and requests into reviewable matter artifacts.

## What this beta now establishes

- One task-oriented workstation for an Agenda, matters, draft creation, work status, and the assistant.
- A deterministic daily advancement review that makes human follow-ups, task dependencies, stale work, case steps, and blockers visible without sending communications.
- Persistent jobs with visible pending, completed, failed, and interrupted states.
- Matter-scoped file intake and summaries instead of an unstructured global chatbot.
- Template provenance warnings and a permanent human-review boundary around generated drafts.
- Local model selection with safe defaults and explicit permission before downloads.
- Default-deny network, email, shell, self-modifying, and document-triggered actions.
- Loopback-only serving, optional token authentication, restrictive browser headers, private runtime files, bounded retention, and reproducible dependency locks.

## Launch gates (P0)

Complete every item in `PUBLIC_BETA_CHECKLIST.md` before inviting users. The highest-risk remaining operational work is:

1. Test the installation and first-run instructions using a clean, non-developer Linux account.
2. Verify every bundled template against an authoritative source and record jurisdiction, revision, source URL, and review date.
3. Exercise backup, restore, rollback, interrupted-job recovery, retention, and deletion with synthetic data.
4. Conduct keyboard-only, screen-reader, reduced-motion, small-screen, light-mode, and dark-mode review.
5. Publish a support route, vulnerability-reporting route, beta privacy notice, known limitations, and stop-ship criteria.
6. Run prompt-injection, malicious archive, path-traversal, XSS, oversized upload, and cross-matter isolation tests in the release environment.

Do not advertise the beta as multi-user, unattended automation, secure cloud hosting, or a professional judgment replacement.

## Recommended beta iterations (P1)

Prioritize improvements that shorten the path from evidence to a reviewed artifact:

1. **Grounded answers with evidence.** Show the matter files and passages used for an answer, provide direct open/download actions, and clearly say when no supporting source was found.
2. **Expand the action review queue.** The beta now represents client communication as an inspectable staff reminder. Extend this pattern to exact-target email drafts, file moves, and other external changes, with separate human confirmation and audit history.
3. **Inline document assistance.** Add an opt-in LibreOffice or ONLYOFFICE integration for selected-text rewrite, summarize, extract dates, and populate fields without copy/paste.
4. **Reusable work recipes.** Turn frequent, reviewed prompts into named actions with required inputs, expected outputs, and explicit permission boundaries.
5. **Unified local search.** Search matter names, filenames, summaries, generated drafts, and job results, with visible scope and source filters.
6. **Feedback at the artifact.** Capture useful/not-useful, corrected outcome, failure category, and optional comments without storing raw client content by default.
7. **Guided first run.** Move model health, storage-root approval, sample matter creation, and privacy choices into a resumable local onboarding flow.

## Later product work (P2)

- Signed desktop packages, verified updates, migration tooling, and an uninstall/data-export flow.
- A real multi-user authorization model, per-matter permissions, audit review, TLS deployment profiles, and secret management.
- Provider abstraction beyond Ollama with a precise per-provider data-flow disclosure and opt-in controls.
- Permission-aware connectors for calendar, mail, cloud files, and meetings.
- Spreadsheet and presentation-native workflows after document and matter workflows are dependable.

## Suggested beta measures

Track measures that expose trust and usability rather than raw prompt volume:

- successful clean installs and median time to first reviewed artifact;
- job success, interruption, retry, and user-corrected failure rates;
- percentage of answers with usable supporting evidence;
- generated drafts accepted, materially edited, or discarded;
- external-action proposals approved, changed, or rejected;
- support incidents involving privacy, cross-matter leakage, lost work, or misleading completion status.

Any confirmed data exposure, cross-matter access, unreviewed external action, unrecoverable data loss, or falsely reported completion should stop new beta onboarding until investigated.

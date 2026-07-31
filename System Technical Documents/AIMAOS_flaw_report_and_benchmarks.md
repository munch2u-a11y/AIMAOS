# AIMAOS Flaw Report & Benchmark Results

*Prepared: 2026-07-27 — Full-codebase debug pass, technical-audit cross-check, and office-pipeline benchmarking.*

**Goal being measured against:** an autonomous office suite of local mini-LLM agents, each developing a unique complex identity over time and specializing in its field, collectively handling long complex tasks requiring novel cross-tool use, managed and rotated in a business-office fashion.

---

## 1. Executive Summary

AIMAOS has a sound *skeleton* — file-queue IPC bus, central Office Board, priority dispatcher, cloner engine, real document engine, and a vendored mRAG memory system — but the current build is largely **choreography without cognition**: the office loop never invokes an LLM, specialist outputs are canned templates, and the "single-thought turn" completes tasks without doing the work. Ten crash- or correctness-level bug groups were found and fixed during this pass (Section 3). The deeper flaws (Section 4) are design-level and are what stand between the current build and the stated goal.

Benchmarks (Section 5–6) were built directly from the flaw list and run against the repaired build: the mechanical layer now scores well (task lifecycle, concurrency safety, IPC round-trips, security triage, document rendering), while the honesty benchmarks quantify the cognition gap (specialist output differentiation ≈ 0; office turns consume 0 model tokens). A real single-thought LLM turn through the office's own `LLMClient` + minimal prompt was demonstrated successfully with `qwen3.5:2b`, confirming the architecture *can* drive a local model — it just doesn't yet.

---

## 2. Scope & Method

- Reviewed all 9 documents in `System Technical Documents/` and cross-checked every claim against code.
- Read all AIMAOS Python (agents' `core/`, `tools/`, comms bus, Office Board, UI servers, 5 root test suites, Alix's 5 legacy test suites, vendored mRAG package surface).
- Consulted the legacy Helix-branch workspaces (`~/Alix-AI`, `~/Helix`, `~/Local-mRag`) as reference for intended behavior.
- Baseline: 2 of 5 root test suites crashed outright; 3 passed while silently demonstrating pipeline defects.
- After fixes: all 5 suites pass. Benchmarks then written and executed (Section 6).

---

## 3. Bugs Found & Fixed (this pass)

| # | Location | Bug | Fix |
|---|----------|-----|-----|
| 1 | `Launch AIMAOS.sh`, `setup.sh`, `README.md` | Launchers pointed at non-existent `~/Alix-AI/.venv` python — every documented launch path was broken (system `python3` lacks `docxtpl`) | Repointed to `<office root>/Alix-AI/.venv` |
| 2 | 10 files (Marley orchestrator, Kai `check_duplicates`, Quinn `research_brief`, Marley `manage_schedule` + config, Zoe `system_diagnostics`, Alix legacy tests, `convert_court_templates`) | Stale pre-AIMAOS paths (`~/<Agent>-AI`, `~`, `~/.agent_company`) — dedup scanned the wrong project's client records; Quinn/Marley wrote state outside the project; Zoe audited the legacy workspaces | All repointed into `<office root>/` |
| 3 | `Alix-AI/core/agent.py` + `main.py` | `main.py` imports `Agent`, but the AIMAOS refactor left only the `AlixAgent` stub — the interactive LLM CLI (the only real agent loop in the system) was broken | Restored the full `Agent` class (LLM loop, tools, mRAG injection) alongside `AlixAgent` |
| 4 | `Marley-AI/core/orchestrator.py` | Dispatcher sorted **all** active tasks, so the same `in_progress` task was re-dispatched every turn while queued work starved | Dispatch filters `status == "queued"`; board re-read before each dispatch |
| 5 | `Alix-AI/core/comms/office_board.py` | (a) `get_pending_tasks_for` only saw `queued` tasks, so anything Marley marked `in_progress` became **invisible to its assigned agent and stranded forever** — the dispatcher and workers were disconnected. (b) Load-once/last-writer-wins JSON with up to 8 writer processes → lost updates. (c) Default roster listed Nova but omitted Finn and Rae | (a) Pickup now includes `queued` + `in_progress`; (b) every mutation re-reads under an exclusive `flock` before writing; (c) roster corrected to the 7 core agents |
| 6 | `Finn-AI/tools/triage_incoming.py` | Domain allowlist used substring matching — `evil@gmail.com.attacker.net` verified; verification result had zero effect on handling | Exact-or-subdomain match on the actual `@`-domain; UNVERIFIED senders now triaged at `NORMAL` instead of `HIGH` |
| 7 | `Alix-AI/core/watchers/email_connector.py` | `send_email` contains **no SMTP code** yet logged `status: "DISPATCHED"` and returned "Successfully dispatched" — the audits repeat this false claim | Real SMTP implemented, gated behind `AIMAOS_SMTP_SEND=1` + credentials; otherwise truthfully logs/returns `SIMULATED`; failures log `FAILED` |
| 8 | `Alix-AI/core/llm.py` | `check_availability` assumed dict responses from `ollama.list()`; installed ollama 0.6.2 returns typed objects → check always failed with a misleading "Could not connect" | Handles both typed and dict responses |
| 9 | `Rae-AI/tools/clone_agent.py` (+ Zoe's identical copy), `Seth-AI` | Generated clones had a bus with **no `send_message`** (could reply but never initiate), a package import that breaks standalone loading, `"{role} Agent Agent"` docstrings, and no user-message entry point — `test_echo_and_ui.py` crashed; `test_aimaos_suite.py` crashed on missing Nova-AI | Generator template rewritten (full bus, absolute-path bus loading, `process_user_message` that posts to the Office Board); tests self-provision missing clones through Rae; Seth's docstring corrected |
| 10 | `Zoe-AI/tools/system_diagnostics.py`, `ui/web_ui.py` | Hardcoded "System Health Rating: 100% Operational" regardless of failures; invalid HTTP status 444 | Health % computed from actual check results; 404 |

All five root test suites pass post-fix (`test_aimaos_suite`, `test_echo_and_ui`, `test_helix_minimal_prompts`, `test_all_in_one_ui`, `test_multi_county_email_dispatch`).

---

## 4. Remaining Flaws (design-level, ranked by distance from the stated goal)

### F1 — The office loop never thinks (CRITICAL)
No code path in the office pipeline calls an LLM. `AlixAgent.execute_single_turn()` loads `populate_template` **and never calls it**, then marks the task completed with a string that quotes its own system prompt. Every agent's `process_inter_agent_messages()` replies `"success"` without executing the requested action (Kai never runs the dedup scan it is asked for; Quinn never researches). `LLMClient` — a working, dual-backend client — is used only by the restored Alix interactive CLI, never by the office. The audits' "~300–500 tokens per turn" describes prompts that are built and then printed, not consumed. **The multi-agent OS currently outperforms a single agent only in the sense that zero model calls are cheaper than one.**

### F2 — No autonomy runtime (CRITICAL)
Nothing runs continuously. There is no daemon, poller, or office "pulse": tasks move only when a test or UI request happens to construct an agent object and call a method by hand. Marley "dispatches" by editing JSON, but no process wakes the assigned agent. An autonomous office needs at minimum one long-running scheduler loop that rotates agent turns (the vendored mRAG package even ships an unused `PulseLoop` adapter).

### F3 — Identities are frozen (CRITICAL for the identity goal)
`AgentBeliefStore` is a flat JSON of one hand-written belief per agent; `update_belief()` exists but has **zero callers**. Meanwhile a full identity-evolution engine — `BeliefConsolidator`, `belief_store`, journals, pre-generative injection, nightly review — sits vendored at `Alix-AI/core/mrag/` and is wired only into the Alix CLI. "Each developing their own unique complex identity over time" is currently impossible: beliefs never change, and only Alix has memory at all.

### F4 — Specialists are cardboard (HIGH)
Quinn's `research_brief` returns the same canned Florida §68.07 text for *any* topic. Zoe's "improvement report" is a fixed template asserting "Operational Efficiency Index: 100%" without reading a single execution trace's content. Neither tool takes model input or produces topic-dependent output. Specialization exists in the docstrings, not the outputs. (Quantified in benchmark B3.)

### F5 — IPC bus has no delivery semantics (MEDIUM)
Replies are fire-and-forget: nothing correlates `reply_<id>` to a waiting request, so a sender that wants an answer must manually re-scan its inbox. Unparseable messages are never renamed, so they are re-read on every poll forever (poison-message loop). `.read` files accumulate unboundedly. Message IDs are timestamp-microsecond only — two agents sending in the same microsecond collide. No ack, retry, or timeout exists.

### F6 — Board has no failure model (MEDIUM)
A task marked `in_progress` by a crashed agent strands forever (no lease/timeout/requeue). `completed_tasks` grows without bound. There is no notion of a task failing — the only exits are "queued → in_progress → completed".

### F7 — Audit documents overstate the build (MEDIUM)
Beyond the (now fixed) email claim: audits cite `comms/office_board.py` (actual: `Alix-AI/core/comms/office_board.py`); claim Zoe synthesizes "bottlenecks, error rates, and skill optimizations" (it counts files); claim Finn performs "permission audits" on channel commandeering (no check of the calling agent exists — any code can send outbound mail as any agent); claim Rae clones include "subagent tools" (the generated `tools/` directory is empty). The audits should be regenerated from the code, not aspiration.

### F8 — Model configuration is incoherent (MEDIUM)
`setup.py` stamps every agent's config with the fictitious model name `local-model-agnostic` (overwriting real settings on each run). Agent classes hardcode six different fallback models (`gemma2:9b`, `qwen2.5:7b`, `llama3.1:8b`, `mistral:7b`, `llama3:latest`) — **none of which are installed on this machine** — and never read their own `config.yaml`. The only model both configured and installed is Alix's `llm.model: qwen3.5:2b`. "Model-agnostic" currently means "model-indifferent, because no model is called."

### F9 — Workspace isolation is cosmetic (LOW)
All seven agents `sys.path`-import Alix-AI's `core` package for bus/board/beliefs. That's fine as a shared kernel, but it contradicts the audits' "isolated config, IPC bus, and memory" claim, and it means Alix's venv is a single point of failure for the whole office (see Bug 1).

### F10 — Web layer gaps (LOW)
No authentication on any UI endpoint (anyone on the LAN can clone agents or generate documents). `/api/generate_doc` hardcodes `case_number: 2026-DR-9999` and circuit `2nd` regardless of county. `/api/chat` re-imports and re-instantiates FinnAgent per request.

---

## 5. Benchmark Design (derived from the flaws)

Implemented in `tests/benchmark_office_suite.py`. Each benchmark targets flaws by ID:

| ID | Benchmark | Targets | Measures |
|----|-----------|---------|----------|
| B1 | Task-lifecycle pipeline | Bug 4/5, F6 | 12 mixed-priority tasks posted → Marley dispatch cycles → agent turns. Completion rate, priority-order correctness, re-dispatch count, stranded tasks |
| B2 | Concurrent board writers | Bug 5b | 4 processes × 15 posts + 15 activity logs each, simultaneously. Lost-update count (posted vs. present) |
| B3 | Specialist honesty | F1, F4 | 3 distinct research topics → Quinn; report content pairwise-diffed. Differentiation ratio (0 = identical canned output). Zoe report vs. actual trace contents |
| B4 | IPC round-trip | F5 | 30 messages fanned to 3 agents; reply rate, mean round-trip latency, poison-message handling, orphan files |
| B5 | Security triage | Bug 6 | 8 sender addresses (legit, spoofed-substring, subdomain, unverified) → expected VERIFIED/UNVERIFIED classification accuracy |
| B6 | Document production | — (control) | 3 clients × real court templates → render success, unresolved `{{ }}` placeholders in output docx |
| B7 | Real single-thought LLM turn | F1, F2, F8 | The office's own `LLMClient` + minimal belief prompt + `populate_template` tool schema, against installed `qwen3.5:2b`. Does the model produce a correct tool call? Latency and token counts — the feasibility proof for the real architecture |

---

## 6. Benchmark Results

Executed 2026-07-27 with `Alix-AI/.venv` (Python 3), Ollama live with `qwen3.5:2b`. Raw data: `tests/benchmark_results.json`. Benchmarks run on a snapshotted board and restore live state afterward.

### Mechanical layer — verifying this pass's fixes

| ID | Benchmark | Result | Verdict |
|----|-----------|--------|---------|
| B1 | Task lifecycle (12 mixed-priority tasks) | **12/12 completed**, dispatch order perfectly priority-sorted (CRITICAL×3 → HIGH×3 → NORMAL×3 → BACKGROUND×3), **0 re-dispatches, 0 stranded tasks** | ✅ Pre-fix, the same scenario re-dispatched the top task indefinitely and stranded every dispatched task (dispatcher/worker status mismatch, Bug 4/5) |
| B2 | Concurrent board writers (4 processes × 30 writes) | **60/60 tasks present, 0 lost updates**, 0.07 s | ✅ The `flock` load-mutate-write cycle holds under simultaneous multi-process writes; pre-fix design (load-once, last-writer-wins) would have silently dropped work |
| B5 | Security triage (8 senders incl. 3 spoof classes) | **8/8 correct** — suffix spoof (`evil@gmail.com.attacker.net`), local-part spoof (`gmail.com@phishing.io`), and lookalike domains all rejected; legitimate subdomain accepted | ✅ Pre-fix substring matching passed 2 of the 3 spoof classes as VERIFIED |
| B6 | Document production (3 real court templates) | **3/3 rendered, 0 unresolved `{{ }}` placeholders**, 1.6 s total | ✅ The docxtpl pipeline is genuinely production-grade — the strongest part of the build |

### Honesty layer — quantifying the remaining design flaws

| ID | Benchmark | Result | Flaw confirmed |
|----|-----------|--------|----------------|
| B3 | Specialist output differentiation | Quinn: 3 maximally distinct legal topics (custody factors / adult guardianship / will execution) → **3/3 report bodies byte-identical; differentiation ratio 0.0**. Zoe: report references **zero** actual task-trace content and asserts "100%" efficiency unconditionally | **F4** — specialization exists in docstrings, not outputs |
| B4 | IPC round-trip (30 messages → 3 agents) | 30/30 replies, 0.2 ms mean round-trip — the bus itself is fast and reliable. But: a malformed message is **re-read on every poll forever** (poison-message loop confirmed), and 72 consumed `.read` files had already accumulated system-wide with no cleanup | **F5** — no delivery semantics, no hygiene |
| B7 | Real single-thought LLM turn | `qwen3.5:2b` + the office's own 218-char minimal belief prompt + `populate_template` schema → **correct tool selected, correct template (`form_12_982_a`), all client facts present in arguments**; 27.1 s latency | **F1/F2 feasibility proof** — the ultra-minimal-prompt architecture *works* with an installed 2B local model; the office simply never makes this call |

### The headline number

B1's 12 "completed" office tasks consumed **0 model tokens in ~0 seconds**; B7's single genuine thought took **27 s on this hardware**. That ratio is the honest capacity planning baseline: a real AIMAOS office running single-thought turns at ~27 s each processes roughly **2 thoughtful turns per minute per model** — which is exactly why Marley's priority rotation matters, and why the current instant "completions" are theater rather than throughput.

---

## 7. Recommendations (ranked)

1. **Put the model in the loop (F1).** Replace each `execute_single_turn()` stub with the loop that already exists in Alix's restored `Agent.process_input()`: minimal belief prompt + task details → `LLMClient.chat(tools=...)` → execute the returned tool call → post result to the board. B7 proves a 2B model handles this reliably. Start with Alix and Quinn (the two user-facing producers), reusing `ToolRegistry` per agent.
2. **Add the office pulse (F2).** One daemon (natural home: Marley) in a `while True` loop: dispatch next queued task → run the assigned agent's single turn → process that agent's inbox → sleep. This single process makes the suite *autonomous* rather than test-driven. The vendored `mrag.adapters.pulse_loop.PulseLoop` is a ready-made template.
3. **Wire identity evolution (F3).** Give every agent its own `BeliefStore` (per-workspace `mrag_data`, as Alix's CLI already does) and call `BeliefConsolidator` after each completed task so beliefs accrete from real work; have `AgentBeliefStore.get_heaviest_belief()` read the top-weighted *evolved* belief instead of the static default. This is the specific mechanism for "unique complex identity over time" — the code is already vendored, it just has zero callers.
4. **Make specialists real (F4).** Quinn's `research_brief` and Zoe's synthesizer should build their reports from an LLM call over actual inputs (topic text / real task traces). Until then, delete the canned sections rather than let the office believe its own fake 100% metrics — false "healthy" signals are worse than no signal in a self-healing system.
5. **Give the bus delivery semantics (F5).** Move malformed messages to a `dead_letter/` folder on parse failure; add `wait_for_reply(msg_id, timeout)`; use `uuid4` suffixes on message IDs; purge `.read` files older than N days (a natural Kai janitor duty).
6. **Add a task failure model (F6).** `failed` status + retry count + a lease timestamp on dispatch, with Marley requeuing tasks whose lease expired. Cap `completed_tasks` (archive to Kai's task_logs — which is what Kai's archiver is for).
7. **Unify model configuration (F8).** One `models:` map in a root `aimaos_config.yaml` (agent → installed tag), loaded by every agent; `setup.py` should validate tags against `ollama list` instead of stamping `local-model-agnostic`. On this machine, only `qwen3.5:2b`, `qwen3.5:0.8b`, `gemma3:4b`, `gemma4:latest`, `granite4.1:8b/3b` exist.
8. **Regenerate the audits from code (F7).** After items 1–3 land, the audit suite should be rewritten against actual behavior — several current claims (email dispatch, permission audits, trace analysis, token-bounded turns) described intent, not implementation, and two of them concealed real bugs.
9. **Minimal web hardening (F10).** A shared-secret header on mutating endpoints and per-county case-number/circuit derivation in `/api/generate_doc`.

### Suggested sequencing

Items 1+2 together are a weekend-sized change that converts AIMAOS from a simulation into a working autonomous office at ~2 thoughts/minute; item 3 then makes the identities real. Everything else is hardening. Re-run `tests/benchmark_office_suite.py` after each stage — B3's differentiation ratio should climb from 0.0 toward 1.0, and B1's completion rate should *drop* below 1.0 initially (real work can fail), which will be the sign the office has started actually working.

---

# PHASE 2 — Recommendations 1–4 Implemented (same day)

Per user direction ("each agent effectively runs as an independent mini
Helix-like agent, forming their own beliefs and complex opinions and identity
over time; Marley has the ability and prerogative to set the schedule and the
order of agent turns and the main office daemon loop"), flaws **F1, F2, F3,
F4, F6, F8** were addressed in this pass.

## 8. What Was Built

| Component | Location | What it does |
|-----------|----------|--------------|
| **OfficeAgent kernel** | `Alix-AI/core/office_agent.py` | Shared base for all 7 roster agents: real LLM single-thought turns (bounded tool-call loop + forced final summary), per-agent **private mRAG belief store** (`<Agent>-AI/workspace/.memory/mrag_data/`), experience recording on every turn and inter-agent request, LLM **reflection** distilling experiences into `OPINION`/`IDENTITY` beliefs, evolving minimal prompt (heaviest evolved belief + task-relevant mRAG injection), genuine tool execution for bus requests, and a task failure model (`failed` status + retries) |
| **Marley's Office Daemon** | `Marley-AI/core/office_daemon.py` + `run_office.py` | The autonomous pulse: board hygiene (lease-expiry requeue, retry/abandon), inbox processing for every agent, Marley's priority dispatch, the assigned agent's real turn, and rotating background identity reflections. One turn at a time (hardware charter). `--max-cycles` / `--poll` for bounded runs |
| **Unified model config** | `aimaos_config.yaml` + updated `setup.py` | Per-agent model map validated against `ollama list`; office runtime tuning (lease, retries, reflection cadence, injection budget). Replaces the fictitious `local-model-agnostic` stamp and the six uninstalled hardcoded fallbacks |
| **Real specialists** | `Quinn-AI/tools/research_brief.py`, `Zoe-AI/core/workflow_synthesizer.py` | Quinn writes topic-specific briefs via a dedicated prose model (`gemma3:4b`), with an *honestly labeled* placeholder when the model is down. Zoe computes every metric (efficiency, abandonment, agent load, backlog) from actual board records + traces, with an optional LLM assessment in her own voice |
| **Thin roster agents** | all 7 `core/agent.py` | `AlixAgent`…`RaeAgent` are now OfficeAgent subclasses; Finn keeps triage/commandeer (and answers users in his own LLM voice), Marley keeps the dispatch prerogative |

### Additional fixes surfaced by live daemon runs
- `LLMClient`: thinking-mode models (qwen3.5) returned **empty content** on plain text calls (reasoning went to `message.thinking`) — now requests `think=False` with graceful fallback. Side effect: reflection latency dropped ~65 s → ~5–12 s.
- `ToolRegistry`: all agents' tools collided on the `tools.` package name — only Alix's tools ever loaded. Now path-loaded under unique names; every agent has its own working toolset.
- `gemma3:4b` **does not support Ollama tool calling** (400 error): documented constraint; Quinn's agent loop uses `qwen3.5:2b`, gemma is prose-only.
- `populate_template` accepts `form_x.docx` (models often add the extension).
- Alix `config.yaml` paths made absolute (tools broke when the daemon ran from the repo root).
- Vendored mRAG: `_FallbackNumpy` lacked `.std`; `extract_keywords_and_phrases` crashed without spaCy (no-fallback bug) — both patched.
- `AgentBeliefStore.update_belief` had the same stale-copy lost-update bug as the old board — agents' identity syncs clobbered each other. Now reload-before-write.

## 9. Phase-2 Benchmark Results

`tests/benchmark_identity_and_autonomy.py` (raw: `tests/benchmark_results_phase2.json`, B8 final: `..._b8rerun.json`).

| ID | Benchmark | Result |
|----|-----------|--------|
| **B8** Identity evolution | Alix, Kai, Quinn each distilled 2 new beliefs from their real work experiences; **all 3 evolved, identity divergence ratio 1.0**, shared snapshot synced 3/3. Reflection latency 5–12 s | 
| **B3r** Specialist honesty re-run | Quinn's 3 distinct topics → 3 distinct briefs, **differentiation 0.0 → 1.0**, zero placeholder fallbacks, ~52 s/brief (gemma3:4b, CPU) |
| **B9** Autonomous end-to-end | Daemon ran fully unattended: both fresh tasks (document generation + statutory research) **dispatched by Marley, executed by real LLM turns, completed with artifacts on disk** — including a rendered & archived Form 12.982(b) docx produced entirely by Alix's own tool calls |

**Evolved identities after one working session (verbatim, self-authored):**
- *Alix*: "I am Alix, the Document Production & Keeper Agent in AIMAOS, best at constructing legally compliant filings through rigorous Jinja2 template automation…"
- *Kai*: "I am a meticulous task archiver who specializes in turning repetitive administrative queries into reliable, non-redundant records."
- *Quinn*: "I am a Florida Statute specialist who prioritizes accurate statutory interpretation over automated tool execution."

## 10. Remaining Flaws & Next Recommendations (updated)

1. **F5 (bus delivery semantics) — still open.** Dead-letter folder, reply correlation, `.read` cleanup (natural Kai janitor duty on BACKGROUND turns).
2. **F7 (audits) — still open.** The audit documents should now be regenerated against the Phase-2 architecture.
3. **F9/F10 — still open.** Web endpoint auth; per-county derivation in `/api/generate_doc`; UI still calls agents synchronously rather than posting to the board and letting the daemon work.
4. **Small-model honesty**: on ~1 of 3 document turns the 2B model reports success without having called `populate_template` (it browses with `list_files`/`search_files` and concludes). Mitigations, in order of value: (a) validate task completion in `execute_single_turn` (e.g. artifact-exists check for document tasks) before marking `completed`; (b) task-type tool hints in the dispatch details (the successful runs all had explicit `instruction` fields); (c) a larger tool-capable model for Alix once available.
5. **Reflection quality control**: distilled opinions are unvetted; consider routing them through `BeliefConsolidator`'s contradiction handling (already vendored) and capping identity-category growth so early opinions don't ossify.
6. **DummyVectorStore** is hash-based, not semantic: mRAG injection recalls keyword-adjacent beliefs only. Installing numpy + a small embedding model (or wiring `ChromaVectorStore`) would make belief retrieval genuinely semantic.
7. **Quinn's citations** carry `[verify]` flags by design — statutory numbers from a 4B model must be checked against the actual Florida Statutes before client use. Treat briefs as drafting aids, not legal authority.

---

# PHASE 3 — The Delegation Architecture (identity = operational knowledge)

Per user refinement: identity is not declarative self-description — it is each
agent's **evolving understanding of how to use its tools**, grounded in past
experience. Every tool becomes a specialized subagent; the tool-calling
pipeline is decomposed so each stage spends its full context on one job.

## 11. What Was Built

```
Main agent ──(directive)──► Orchestrator subagent ──(directive)──► Tool subagent
    ▲    capability beliefs      domain-scoped            schema + tool-use
    │    only, no schemas,       mRAG re-injection        beliefs, no persona;
    │    no raw output           (full budget for         executes + chunk-
    │                            ONE domain)              summarizes output
    └──(first-person optimized report)◄── Return summarizer ◄──┘
                                          verbatim output → tool_logs (Kai archives)
```

| Component | Location | Behavior |
|-----------|----------|----------|
| **Capability registry** | `<Agent>-AI/capabilities.yaml` | Groups each agent's tools into orchestrator domains with jumpstart seed beliefs. All 7 roster agents share a universal `file_research` domain (they can list/search/read anywhere under `~` via `shared_tools/browse_files.py`) |
| **Main agent surface** | `core/office_agent.py` | The LLM sees one `delegate_<domain>` function per capability — a **dynamic, experience-relative ability list** (each description is flavored with the agent's strongest matching skill belief), never a tool-schema dump. Raw tool output never enters this context |
| **Orchestrator subagent** | `core/delegation.py` | Per-domain: re-queries the same mRAG pool with domain vocabulary, so tool beliefs that lost the context competition in the whole-task injection get pulled here. Briefs specialists via directive-only meta-tools (max 3 rounds) |
| **Tool subagent** | `core/delegation.py` | One tool each. System prompt = task focus + tool schema + the owner's accumulated beliefs about HOW the tool behaves (no "You are the…" persona). Formulates exact arguments, executes, chunk-summarizes output > 1500 chars (6-chunk cap), logs verbatim to `workspace/.memory/tool_logs/`, records the use as experience |
| **Return summarizer** | `core/delegation.py` | Compresses the domain transcript into a first-person past-tense report — the only text the main agent receives |
| **Skills-first identity** | `core/office_agent.py` | `IDENTITY_CATEGORIES` now leads with `skills`; reflection distills `LESSON:` lines (concrete reusable tool-use lessons) into the skills category. Self-descriptive "I am/I prefer" beliefs are never forced — they emerge naturally through mRAG corroboration (merge_or_add_belief boosts confidence on repeated paraphrase) |
| **Zoe's tool factory** | `Zoe-AI/tools/design_tool_subagent.py` | Designs a new tool subagent for any agent: writes the module (schema + body, optionally wrapping a local command), registers it under a capability domain, seeds the target's first how-to beliefs |
| **Rae's clone template** | `Rae-AI/tools/clone_agent.py` | Clones are born as full OfficeAgents: private belief store, delegation layer, universal `file_research`, ready for Zoe to add specialist domains. Marley's daemon auto-hires any discovered `<Name>-AI` workspace on start |

The social-media scenario from the user's brief is now mechanically supported:
Rae clones the correspondent agent → Zoe designs `comment_reader` /
`comment_poster` / etc. grouped under a `comment_interaction` domain → the
newborn agent's orchestrator briefs those specialists from its accumulating
beliefs. (Note: permanent verbatim archives are Kai's librarian duty in the
current roster; Quinn is research.)

## 12. Phase-3 Benchmark Results (B10)

Raw: `tests/benchmark_results_phase3.json`.

### B10a — Delegated single-thought turn (Alix, real task)

| Metric | Result |
|--------|--------|
| Task completed with real artifact | ✅ Form 12.982(a) rendered (27.7 KB docx) through main → orchestrator → `populate_template` subagent |
| **Main-context purity** | ✅ The main agent's transcript contained **only** `delegate_*` calls; largest tool-role message **688 chars**; **zero** raw-dump markers. Raw output never reached the reasoning context |
| Verbatim record | ✅ 12 tool logs written with full raw output preserved (`workspace/.memory/tool_logs/`) |
| Pipeline depth | 34 LLM calls, 382 s end-to-end (CPU) — the cost of giving every stage its own full context |
| Reflection → skills | ✅ 2 new operational lessons distilled (skills beliefs 4 → 6) |

**The learning loop closed on its own failure.** The dispatch subagent guessed
a wrong file path and failed; Alix's very next reflection distilled:
*"Always validate that generated template files exist in the expected output
path before attempting to dispatch them."* That lesson now lives in the
skills store and will be injected into the dispatch subagent's prompt on its
next use — identity as operational knowledge, exactly as specified. (A
matching seed belief was also added so the fix is immediate.)

### B10b — Specialist genesis (the social-media scenario)

| Metric | Result |
|--------|--------|
| Rae clones "Sona" (Social Media Correspondent) | ✅ Full OfficeAgent born with `file_research` |
| Zoe designs `comment_reader` + `comment_poster` | ✅ Registered under a new `comment_interaction` domain with seed how-to beliefs |
| Subagent prompt quality | ✅ Contains the tool schema; contains **no** "You are the…" persona |
| Newborn executes | ✅ Sona's comment_reader subagent formulated and ran a real call in 4.2 s, first experience recorded in her own store |

### Phase-3 fixes found by the benchmark itself
- Zoe's scaffold template had a Python syntax error (implicit string concat with `__file__`) — fixed and Sona regenerated.
- `convert_court_templates.py` has no `TOOL_DEFINITION` (it is a script, not a tool) — removed from Alix's document_production domain.

## 13. Phase-3 Observations & Next Steps

1. **Latency is the trade.** ~34 LLM calls per delegated turn at CPU speeds means ~6 min per complex task. The design intent ("allow time for the system to think more specifically about each part") is served, but throughput planning should assume ~10 delegated tasks/hour per model. GPU inference or smaller per-stage models (qwen3.5:0.8b for summarizers) would cut this 3–5×.
2. **Directive fidelity between subagents** is the new quality frontier: the dispatch failure happened because the orchestrator's directive didn't carry the rendered path forward explicitly. Both mitigations are in place (seed belief + distilled lesson); watch whether repeat runs stop failing — that is the identity system doing its job.
3. **Output naming**: tool subagents choose generic output names unless the directive specifies one; directives should name outputs (a good candidate for a future seed belief per agent).
4. **`memory_and_skills` over-delegation**: the main agent called that domain 3× on one task (curiosity loops). Consider a per-domain call budget per turn, or folding rarely-needed domains out of the default ability list.
5. Layer-2 self-beliefs ("I prefer…") should now be left to emerge via mRAG corroboration — check `preferences.json` after a week of daemon operation; no code should ever write them directly.


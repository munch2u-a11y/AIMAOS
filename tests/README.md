# AIMAOS Tests and Benchmark Suites

The default release gate is isolated and does not require a model or mutate live office data:

```text
Windows: .\.venv\Scripts\python.exe -m pip install -r requirements-dev.lock
         .\.venv\Scripts\python.exe -m pytest -q
Linux:   .venv/bin/python3 -m pip install -r requirements-dev.lock
         .venv/bin/python3 -m pytest -q
```

Pytest is configured to collect only `tests/unit/`. The older scripts below are manual integration and benchmark programs; run them by filename only after reading their side effects.

Run everything from the office root with the interpreter that has the
dependencies installed:

```text
Windows: .\.venv\Scripts\python.exe tests\<suite>.py
Linux:   .venv/bin/python3 tests/<suite>.py
```

**These are integration suites, not unit tests.** Several drive real local
LLM turns, so runtimes depend entirely on your hardware and model sizes. On
CPU inference with a 2B model, a single fully delegated agent turn is
roughly 30 model calls and can take 5–25 minutes. Nothing is hanging — watch
`ollama ps` or the office board if you want to confirm progress.

| Suite | Real LLM calls | Typical CPU runtime | What it covers |
| :--- | :--- | :--- | :--- |
| `test_aimaos_suite.py` | no | seconds | Office Board lifecycle, IPC bus round-trips, Kai archiving, Zoe synthesis |
| `test_echo_and_ui.py` | no | seconds | Setup wizard, Rae clone provisioning, board state |
| `test_all_in_one_ui.py` | yes (one chat) | ~1 min | Dashboard HTTP endpoints, document studio, agent cloning |
| `test_multi_county_email_dispatch.py` | no | ~1 min | Multi-client intake, form rendering, gateway dispatch logging |
| `test_helix_minimal_prompts.py` | yes (full turns) | 5–25 min | Minimal prompts, model matrix, real single-thought turn execution |
| `benchmark_office_suite.py` | one turn | ~5 min | B1–B7: lifecycle, concurrency, IPC, triage, rendering, one real LLM turn |
| `benchmark_identity_and_autonomy.py` | many | 20–40 min | B8/B3r/B9: belief evolution, specialist output differentiation, unattended daemon run |
| `benchmark_delegation.py` | many | 10–30 min | B10: delegation pipeline purity, verbatim logging, specialist genesis |

Benchmarks write raw results to `tests/benchmark_results*.json` (git-ignored).

## Notes

- Suites operate on the **live** office board and agent belief stores; they
  post real tasks and record real experiences. `benchmark_office_suite.py`
  snapshots and restores the board around its run, the others do not.
- Agent turn-loops need a tool-calling-capable model. If a suite reports
  `does not support tools (status code: 400)`, reassign that agent's model in
  `aimaos_config.yaml`.
- Keep email `READ_ONLY`, network/external mutations disabled, and
  `AIMAOS_SMTP_SEND` unset for tests. A deliberately reconfigured integration
  script can otherwise perform a real external action; do not run manual suites
  against production credentials or data.

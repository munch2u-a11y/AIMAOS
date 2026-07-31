"""
AIMAOS Phase-2 Benchmarks: Identity Evolution & Autonomous Operation
====================================================================
B8  — Identity evolution: agents form new beliefs/opinions from real work
      and their identities diverge from each other.
B3r — Specialist honesty re-run: Quinn's briefs are now model-generated,
      so distinct topics must yield distinct content.
B9  — Autonomous end-to-end: Marley's daemon completes real tasks with
      real artifacts, unattended.

Run: python3 tests/benchmark_identity_and_autonomy.py
Writes tests/benchmark_results_phase2.json.
"""
import os

def _find_aimaos_root():
    p = os.path.dirname(os.path.abspath(__file__))
    while p != os.path.dirname(p) and not os.path.exists(os.path.join(p, "aimaos_config.yaml")):
        p = os.path.dirname(p)
    return p
AIMAOS_ROOT = os.environ.get("AIMAOS_ROOT") or _find_aimaos_root()
import re
import sys
import json
import glob
import time
import subprocess
import importlib.util
from datetime import datetime

AIMAOS = AIMAOS_ROOT
VENV_PY = sys.executable  # same interpreter running this benchmark
sys.path.insert(0, AIMAOS)

from core.comms.office_board import OfficeBoard
from core.comms.bus import AgentCompanyBus

RESULTS = {"run_at": datetime.now().isoformat(), "benchmarks": {}}


def load_module(mod_name, file_path):
    spec = importlib.util.spec_from_file_location(mod_name, file_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


def load_agent(name):
    mod = load_module(f"bench2_{name.lower()}", f"{AIMAOS}/{name}-AI/core/agent.py")
    return getattr(mod, f"{name}Agent")()


# ---------------------------------------------------------------- B8
def bench_identity_evolution():
    """Agents accumulate experiences from real work, reflect with their own
    LLM, and their evolved identities must (a) change and (b) diverge."""
    print("\n=== B8: IDENTITY EVOLUTION ===")
    agents = {n: load_agent(n) for n in ["Alix", "Kai", "Quinn"]}

    before = {}
    for name, a in agents.items():
        flat = a.identity_store.get_all_beliefs_flat()
        before[name] = {
            "heaviest": a.get_heaviest_identity_belief(),
            "belief_count": len(flat),
            "identity_beliefs": len([b for b in flat if b.get("_category") in ("premises", "preferences")]),
        }

    # Give Kai and Quinn real work through the bus (real tool executions ->
    # real experiences). Alix already has experiences from daemon turns.
    alix_bus = AgentCompanyBus("Alix")
    alix_bus.read_inbox(mark_read=True)  # drain stale
    alix_bus.send_message("Kai", "check_duplicates", {"query_text": "Alex Sample name change"})
    alix_bus.send_message("Kai", "check_duplicates", {"query_text": "Miller dissolution financial affidavit"})
    agents["Kai"].process_inter_agent_messages()

    # Quinn: one real (LLM) research brief execution as work experience
    t0 = time.time()
    quinn_res = agents["Quinn"].tools.execute_tool(
        "research_brief", {"topic": "Florida Statute 61.19 bifurcated dissolution proceedings", "scope": "procedural"})
    agents["Quinn"].record_experience(
        f"I produced a research brief on bifurcated dissolution. Result: {str(quinn_res)[:200]}")
    quinn_work_sec = round(time.time() - t0, 1)

    # Reflection turns: each agent distills experience -> opinion + identity
    reflections = {}
    for name, a in agents.items():
        t0 = time.time()
        out = a.reflect()
        reflections[name] = {"latency_sec": round(time.time() - t0, 1),
                             "summary": str(out)[:300]}
        print(f"  [{name} reflect {reflections[name]['latency_sec']}s] {str(out)[:160]}")

    after = {}
    for name, a in agents.items():
        flat = a.identity_store.get_all_beliefs_flat()
        after[name] = {
            "heaviest": a.get_heaviest_identity_belief(),
            "belief_count": len(flat),
            "identity_beliefs": len([b for b in flat if b.get("_category") in ("premises", "preferences")]),
        }

    evolved = {n: after[n]["identity_beliefs"] > before[n]["identity_beliefs"]
               or after[n]["heaviest"] != before[n]["heaviest"]
               for n in agents}
    heaviest_set = {after[n]["heaviest"] for n in agents}
    divergence = round((len(heaviest_set) - 1) / max(len(agents) - 1, 1), 3)

    # Shared snapshot sync check
    try:
        with open(f"{AIMAOS}/comms/mrag_agent_beliefs.json") as f:
            shared = json.load(f)
    except Exception:
        shared = {}
    synced = {n: shared.get(n) == after[n]["heaviest"] for n in agents}

    res = {
        "agents_tested": list(agents),
        "before": before,
        "after": after,
        "agents_evolved": evolved,
        "all_evolved": all(evolved.values()),
        "identity_divergence_ratio": divergence,
        "shared_snapshot_synced": synced,
        "reflections": reflections,
        "quinn_real_work_sec": quinn_work_sec,
    }
    print(json.dumps({k: res[k] for k in
                      ["agents_evolved", "identity_divergence_ratio", "shared_snapshot_synced"]}, indent=2))
    return res


# ---------------------------------------------------------------- B3r
def bench_specialist_honesty_rerun():
    """Quinn's briefs are now model-generated: distinct topics must produce
    distinct substantive bodies (was 0.0 differentiation with canned text)."""
    print("\n=== B3r: SPECIALIST HONESTY RE-RUN (Quinn real research) ===")
    quinn_tool = load_module("bench2_quinn_brief", f"{AIMAOS}/Quinn-AI/tools/research_brief.py")
    topics = [
        "Florida Statute 61.13 child custody time-sharing factors",
        "Chapter 744 guardianship of incapacitated adults",
        "Florida Statute 732.502 execution requirements for wills",
    ]
    bodies, latencies, placeholders = [], [], 0
    for t in topics:
        t0 = time.time()
        out = quinn_tool.execute(t, scope="statutory")
        latencies.append(round(time.time() - t0, 1))
        if "PLACEHOLDER" in out:
            placeholders += 1
        reports = sorted(glob.glob(f"{AIMAOS}/Quinn-AI/workspace/reports/brief_*.md"))
        with open(reports[-1]) as f:
            text = f.read()
        body = "\n".join(l for l in text.splitlines() if t not in l and "Generated" not in l)
        bodies.append(body)
        print(f"  [{latencies[-1]}s] {t[:60]} -> {len(body)} chars")

    identical_pairs = sum(1 for i in range(len(bodies)) for j in range(i + 1, len(bodies))
                          if bodies[i] == bodies[j])
    total_pairs = len(bodies) * (len(bodies) - 1) // 2
    res = {
        "topics_tested": len(topics),
        "identical_body_pairs": f"{identical_pairs}/{total_pairs}",
        "differentiation_ratio": round(1 - identical_pairs / total_pairs, 3),
        "placeholder_fallbacks": placeholders,
        "mean_brief_latency_sec": round(sum(latencies) / len(latencies), 1),
    }
    print(json.dumps(res, indent=2))
    return res


# ---------------------------------------------------------------- B9
def bench_autonomous_daemon():
    """Post fresh tasks, launch Marley's daemon unattended, verify genuine
    completions with real artifacts and zero human intervention."""
    print("\n=== B9: AUTONOMOUS OFFICE DAEMON END-TO-END ===")
    board = OfficeBoard()
    marker = f"bench9_{datetime.now().strftime('%H%M%S')}"
    doc_task = board.post_task(
        f"Generate Adult Name Change Final Judgment for client Rio Sample [{marker}]",
        "Benchmark", "Alix", "CRITICAL",
        details={"template": "form_12_982_b", "client_name": "Rio Sample",
                 "county": "Leon", "circuit_number": "2nd",
                 "case_number": "2026-DR-7777", "new_name": "Rio Newname",
                 "instruction": "Use populate_template with template_name form_12_982_b and this context, "
                                "then dispatch_document to archive the output."})
    research_task = board.post_task(
        f"Research brief: minor child relocation under FS 61.13001 [{marker}]",
        "Benchmark", "Quinn", "CRITICAL",
        details={"topic": "Florida Statute 61.13001 parental relocation with a child",
                 "instruction": "Use the research_brief tool."})

    t0 = time.time()
    proc = subprocess.run(
        [VENV_PY, f"{AIMAOS}/run_office.py", "--max-cycles", "3", "--poll", "1"],
        capture_output=True, text=True, timeout=900)
    elapsed = round(time.time() - t0, 1)

    board.board = board._load_board()
    completed = {t["id"]: t for t in board.board["completed_tasks"]}
    doc_done = doc_task in completed
    research_done = research_task in completed

    doc_result = str(completed.get(doc_task, {}).get("result", ""))
    research_result = str(completed.get(research_task, {}).get("result", ""))

    # Artifact checks: did a real file land on disk?
    doc_files = [p for p in re.findall(r"(/home/\S+?\.docx)", doc_result) if os.path.exists(p)]
    brief_files = [p for p in re.findall(r"(/home/\S+?\.md)", research_result) if os.path.exists(p)]

    res = {
        "daemon_ran_unattended": proc.returncode == 0,
        "elapsed_sec": elapsed,
        "doc_task_completed": doc_done,
        "doc_artifacts_on_disk": doc_files,
        "research_task_completed": research_done,
        "research_artifacts_on_disk": brief_files,
        "doc_result_preview": doc_result.replace("\n", " ")[:250],
        "research_result_preview": research_result.replace("\n", " ")[:250],
    }
    print(json.dumps(res, indent=2))
    return res


def main():
    print("====================================================================")
    print("AIMAOS PHASE-2 BENCHMARKS: IDENTITY & AUTONOMY (B8, B3r, B9)")
    print("====================================================================")
    RESULTS["benchmarks"]["B8_identity_evolution"] = bench_identity_evolution()
    RESULTS["benchmarks"]["B3r_specialist_honesty"] = bench_specialist_honesty_rerun()
    RESULTS["benchmarks"]["B9_autonomous_daemon"] = bench_autonomous_daemon()

    out = f"{AIMAOS}/tests/benchmark_results_phase2.json"
    with open(out, "w") as f:
        json.dump(RESULTS, f, indent=2)
    print("\n====================================================================")
    print(f"PHASE-2 BENCHMARKS COMPLETE. Raw results: {out}")
    print("====================================================================")


if __name__ == "__main__":
    main()

"""
AIMAOS Phase-3 Benchmark: the Delegation Pipeline (B10)
=======================================================
B10a — Delegated single-thought turn: main agent plans over capability
       beliefs, orchestrator briefs tool subagents, return summarizer reports
       back. Verifies: task completed with a real artifact, the main agent's
       context stayed free of raw tool output, verbatim logs preserved, and
       reflection distilled a reusable tool-use LESSON into skills.
B10b — Specialist genesis: Rae clones a Social Media Correspondent, Zoe
       designs its tool subagents (comment_reader, comment_poster) grouped
       under a comment_interaction domain, and the newborn agent executes a
       tool subagent through its own belief-informed prompt.

Run: python3 tests/benchmark_delegation.py
Writes tests/benchmark_results_phase3.json.
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
import importlib.util
from datetime import datetime

AIMAOS = AIMAOS_ROOT
sys.path.insert(0, AIMAOS)

from core.comms.office_board import OfficeBoard

RESULTS = {"run_at": datetime.now().isoformat(), "benchmarks": {}}


def load_module(mod_name, file_path):
    spec = importlib.util.spec_from_file_location(mod_name, file_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


def load_agent(name):
    mod = load_module(f"b10_{name.lower()}", f"{AIMAOS}/{name}-AI/core/agent.py")
    return getattr(mod, f"{name}Agent")()


def count_llm_calls(agent):
    """Wraps the agent's llm.chat with a counter."""
    counter = {"calls": 0}
    original = agent.llm.chat

    def counting_chat(*args, **kwargs):
        counter["calls"] += 1
        return original(*args, **kwargs)

    agent.llm.chat = counting_chat
    return counter


# ---------------------------------------------------------------- B10a
def bench_delegated_turn():
    print("\n=== B10a: DELEGATED SINGLE-THOUGHT TURN (Alix) ===")
    board = OfficeBoard()
    alix = load_agent("Alix")
    assert alix.delegation_enabled, "delegation must be enabled"
    counter = count_llm_calls(alix)

    skills_before = len([b for b in alix.identity_store.get_all_beliefs_flat()
                         if b.get("_category") == "skills"])
    logs_before = set(glob.glob(f"{AIMAOS}/Alix-AI/workspace/.memory/tool_logs/*.json"))

    task_id = board.post_task(
        "Generate Adult Name Change Petition for client Kit Sample",
        "Benchmark", "Alix", "CRITICAL",
        details={"template": "form_12_982_a", "client_name": "Kit Sample",
                 "county": "Leon", "circuit_number": "2nd",
                 "case_number": "2026-DR-8888", "new_name": "Kit Newname",
                 "instruction": "Delegate to document production: render form_12_982_a "
                                "with this context, then archive the output."})

    t0 = time.time()
    outcome = alix.execute_single_turn(task_id=task_id)
    elapsed = round(time.time() - t0, 1)

    board.board = board._load_board()
    completed = any(t["id"] == task_id for t in board.board["completed_tasks"])

    # Main-context purity: no tool-role message in the MAIN agent transcript
    # may carry raw tool dumps — delegation returns must stay compact reports.
    tool_msgs = [m["content"] for m in alix.last_turn_messages if m.get("role") == "tool"]
    max_tool_msg = max((len(m) for m in tool_msgs), default=0)
    raw_markers = sum(1 for m in tool_msgs
                     if "[FILE]" in m or "Content of /" in m or m.count("\n") > 25)
    delegate_names = [m.get("name", "") for m in alix.last_turn_messages if m.get("role") == "tool"]
    used_delegates_only = all(n.startswith("delegate_") for n in delegate_names) and bool(delegate_names)

    # Artifact + verbatim logs
    artifacts = [p for p in glob.glob(
        f"{AIMAOS}/Alix-AI/workspace/output/**/*kit*sample*.docx", recursive=True)]
    artifacts += [p for p in glob.glob(
        f"{AIMAOS}/Alix-AI/workspace/output/**/kit_sample*/**/*.docx", recursive=True)]
    new_logs = set(glob.glob(f"{AIMAOS}/Alix-AI/workspace/.memory/tool_logs/*.json")) - logs_before
    logs_have_raw = False
    for lp in new_logs:
        with open(lp) as f:
            if len(json.load(f).get("raw_output", "")) > 0:
                logs_have_raw = True
                break

    # Reflection -> operational LESSON in skills
    reflect_out = alix.reflect()
    skills_after = len([b for b in alix.identity_store.get_all_beliefs_flat()
                        if b.get("_category") == "skills"])

    res = {
        "task_completed": completed,
        "elapsed_sec": elapsed,
        "llm_calls_total_pipeline": counter["calls"],
        "main_context_used_delegates_only": used_delegates_only,
        "main_context_delegate_calls": delegate_names,
        "main_context_max_tool_msg_chars": max_tool_msg,
        "main_context_raw_dump_markers": raw_markers,
        "artifact_on_disk": sorted(set(artifacts))[:3],
        "verbatim_tool_logs_written": len(new_logs),
        "verbatim_logs_contain_raw_output": logs_have_raw,
        "skills_beliefs_before_after": [skills_before, skills_after],
        "reflection_distilled_lesson": skills_after > skills_before,
        "outcome_preview": str(outcome).replace("\n", " ")[:220],
    }
    print(json.dumps(res, indent=2))
    return res


# ---------------------------------------------------------------- B10b
def bench_specialist_genesis():
    print("\n=== B10b: SPECIALIST GENESIS (Rae clones, Zoe designs tools) ===")
    rae_clone = load_module("b10_rae_clone", f"{AIMAOS}/Rae-AI/tools/clone_agent.py")
    zoe_factory = load_module("b10_zoe_factory", f"{AIMAOS}/Zoe-AI/tools/design_tool_subagent.py")

    import shutil
    if os.path.exists(f"{AIMAOS}/Sona-AI"):
        shutil.rmtree(f"{AIMAOS}/Sona-AI")

    clone_msg = rae_clone.execute("Sona", "Social Media Correspondent")
    print("  [Rae]", clone_msg.splitlines()[0])

    t1 = zoe_factory.execute(
        target_agent="Sona", tool_name="comment_reader",
        description="Reads the latest comments in a local feed file for a topic.",
        parameters_schema={"topic": {"type": "string", "description": "Topic/thread to read comments for."}},
        required_params=["topic"], domain="comment_interaction",
        domain_description="Read and write comments in social feeds.",
        seed_beliefs=["comment_reader returns newest-first; read before posting so replies have context."],
        command_template="echo 'MOCK FEED [{topic}]: user_a: great point | user_b: source? | user_c: following'")
    t2 = zoe_factory.execute(
        target_agent="Sona", tool_name="comment_poster",
        description="Posts a comment reply to a thread in the local feed.",
        parameters_schema={"topic": {"type": "string"}, "text": {"type": "string", "description": "Comment text to post."}},
        required_params=["topic", "text"], domain="comment_interaction",
        seed_beliefs=["comment_poster should quote the specific point it replies to; short comments perform better."])
    print("  [Zoe]", t1.splitlines()[0])
    print("  [Zoe]", t2.splitlines()[0])

    # The newborn agent loads with its designed capability and runs a tool
    # subagent through its own belief-informed minimalist prompt.
    sona = load_agent("Sona")
    from core.delegation import ToolSubagent
    sa = ToolSubagent(sona, f"{AIMAOS}/Sona-AI/tools/comment_reader.py")
    prompt = sa.system_prompt("read the latest comments about the office launch thread")
    t0 = time.time()
    result = sa.run("Read the latest comments on the 'office launch' topic and note who is asking for sources.")
    latency = round(time.time() - t0, 1)
    print(f"  [Sona/comment_reader {latency}s] {str(result)[:180]}")

    res = {
        "clone_created": os.path.exists(f"{AIMAOS}/Sona-AI/core/agent.py"),
        "sona_domains": sorted(sona.domains),
        "tools_designed": ["comment_reader", "comment_poster"],
        "subagent_prompt_has_schema": '"comment_reader"' in prompt,
        "subagent_prompt_has_no_persona": "You are the" not in prompt,
        "subagent_executed_real_call": "MOCK FEED" in str(result),
        "subagent_latency_sec": latency,
        "sona_experiences_recorded": len([b for b in sona.identity_store.get_all_beliefs_flat()
                                          if b.get("_category") == "memory"]),
    }
    print(json.dumps(res, indent=2))
    return res


def main():
    print("====================================================================")
    print("AIMAOS PHASE-3 BENCHMARK: DELEGATION PIPELINE (B10)")
    print("====================================================================")
    RESULTS["benchmarks"]["B10a_delegated_turn"] = bench_delegated_turn()
    RESULTS["benchmarks"]["B10b_specialist_genesis"] = bench_specialist_genesis()

    out = f"{AIMAOS}/tests/benchmark_results_phase3.json"
    with open(out, "w") as f:
        json.dump(RESULTS, f, indent=2)
    print("\n====================================================================")
    print(f"PHASE-3 BENCHMARK COMPLETE. Raw results: {out}")
    print("====================================================================")


if __name__ == "__main__":
    main()

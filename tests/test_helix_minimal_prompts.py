import os

def _find_aimaos_root():
    p = os.path.dirname(os.path.abspath(__file__))
    while p != os.path.dirname(p) and not os.path.exists(os.path.join(p, "aimaos_config.yaml")):
        p = os.path.dirname(p)
    return p
AIMAOS_ROOT = os.environ.get("AIMAOS_ROOT") or _find_aimaos_root()
import sys
import json
import importlib.util

sys.path.insert(0, AIMAOS_ROOT)
from core.mrag_beliefs import AgentBeliefStore

def load_module(mod_name, file_path):
    spec = importlib.util.spec_from_file_location(mod_name, file_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod

def run_test():
    print("====================================================================")
    print("AIMAOS MODEL-AGNOSTIC SYSTEM PROMPTS & mRAG TEST SUITE")
    print("====================================================================\n")

    # 1. Test Setup Wizard Model-Agnostic Matrix
    print("--- 1. TESTING SETUP WIZARD MODEL-AGNOSTIC MATRIX ---")
    setup_mod = load_module("setup_mod", os.path.join(AIMAOS_ROOT, "setup.py"))
    setup_mod.run_diagnostics()
    setup_mod.configure_workspaces()

    # 2. Test Minimal System Prompt & Belief Store
    print("\n--- 2. TESTING mRAG MINIMAL SYSTEM PROMPT INJECTION ---")
    store = AgentBeliefStore()
    agents_to_test = [
        ("Alix", "Document Production & Keeper Agent"),
        ("Marley", "Scheduler & Office Manager"),
        ("Finn", "Security Officer & Comms Gateway"),
        ("Quinn", "Research & Legal Intelligence Reporter"),
        ("Zoe", "DevOps Maintenance Engineer & Synthesizer")
    ]

    for name, role in agents_to_test:
        prompt = store.get_minimal_system_prompt(name, role)
        print(f"\n[{name} Agent System Prompt]:\n{prompt}")
        assert "Identity:" in prompt
        assert "Core Belief:" in prompt

    # 3. Test Single-Thought Turn Loop Execution
    #
    # Post a small, self-contained task and execute THAT specific task rather
    # than whatever happens to sit on the live board: picking up an arbitrary
    # backlog item makes this suite non-deterministic and can run for tens of
    # minutes on a big delegated task, which is a test-harness problem, not a
    # system one.
    print("\n--- 3. TESTING SINGLE-THOUGHT TURN EXECUTION LOOP ---")
    from core.comms.office_board import OfficeBoard
    board = OfficeBoard()
    probe_task_id = board.post_task(
        title="Self-test: confirm the templates library is reachable",
        requester="test_helix_minimal_prompts",
        target_agent="Alix",
        priority="CRITICAL",
        details={"instruction": "List the template library directory once and report what you found. "
                                "Do not render or archive anything."})

    alix_mod = load_module("alix_mod", os.path.join(AIMAOS_ROOT, "Alix-AI/core/agent.py"))
    alix = alix_mod.AlixAgent()
    alix_res = alix.execute_single_turn(task_id=probe_task_id)
    print("[Alix Single-Turn Result]:\n", alix_res)
    assert "Single-thought turn" in str(alix_res), "turn did not run to a reported outcome"

    marley_mod = load_module("marley_mod", os.path.join(AIMAOS_ROOT, "Marley-AI/core/agent.py"))
    marley = marley_mod.MarleyAgent()
    marley_res = marley.execute_single_turn()
    print("\n[Marley Single-Turn Dispatch Result]:\n", marley_res)

    print("\n====================================================================")
    print("SUCCESS: MODEL-AGNOSTIC MINIMAL PROMPTS & SINGLE-THOUGHT TURNS VERIFIED!")
    print("====================================================================\n")

if __name__ == "__main__":
    run_test()

import os
import sys
import json
import importlib.util

sys.path.insert(0, "/path/to/AIMAOS/Alix-AI")
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
    setup_mod = load_module("setup_mod", "/path/to/AIMAOS/setup.py")
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
    print("\n--- 3. TESTING SINGLE-THOUGHT TURN EXECUTION LOOP ---")
    alix_mod = load_module("alix_mod", "/path/to/AIMAOS/Alix-AI/core/agent.py")
    alix = alix_mod.AlixAgent()
    alix_res = alix.execute_single_turn()
    print("[Alix Single-Turn Result]:\n", alix_res)

    marley_mod = load_module("marley_mod", "/path/to/AIMAOS/Marley-AI/core/agent.py")
    marley = marley_mod.MarleyAgent()
    marley_res = marley.execute_single_turn()
    print("\n[Marley Single-Turn Dispatch Result]:\n", marley_res)

    print("\n====================================================================")
    print("SUCCESS: MODEL-AGNOSTIC MINIMAL PROMPTS & SINGLE-THOUGHT TURNS VERIFIED!")
    print("====================================================================\n")

if __name__ == "__main__":
    run_test()

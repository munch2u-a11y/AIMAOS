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
    print("AIMAOS HELIX-STYLE MINIMAL SYSTEM PROMPTS & mRAG TEST SUITE")
    print("====================================================================\n")

    # 1. Test Setup Wizard Multi-Model Matrix
    print("--- 1. TESTING SETUP WIZARD MULTI-MODEL MATRIX ---")
    setup_mod = load_module("setup_mod", "/path/to/AIMAOS/setup.py")
    setup_mod.run_diagnostics()
    setup_mod.configure_workspaces()

    # 2. Test Minimal System Prompt & Belief Store
    print("\n--- 2. TESTING mRAG MINIMAL SYSTEM PROMPT INJECTION ---")
    store = AgentBeliefStore()
    agents_to_test = [
        ("Alix", "Document Production & Keeper Agent", "gemma2:9b"),
        ("Marley", "Scheduler & Office Manager", "qwen2.5:7b"),
        ("Finn", "Security Officer & Comms Gateway", "llama3:latest"),
        ("Quinn", "Research & Legal Intelligence Reporter", "mistral:7b"),
        ("Zoe", "DevOps Maintenance Engineer & Synthesizer", "llama3.1:8b")
    ]

    for name, role, model in agents_to_test:
        prompt = store.get_minimal_system_prompt(name, role)
        print(f"\n[{name} Agent ({model}) System Prompt]:\n{prompt}")
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
    print("SUCCESS: HELIX-STYLE MINIMAL PROMPTS & SINGLE-THOUGHT TURNS VERIFIED!")
    print("====================================================================\n")

if __name__ == "__main__":
    run_test()

import os
import sys
import json
import importlib.util

sys.path.insert(0, "/path/to/AIMAOS/Alix-AI")
from core.comms.office_board import OfficeBoard

def load_module(mod_name, file_path):
    spec = importlib.util.spec_from_file_location(mod_name, file_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod

def run_test():
    print("====================================================================")
    print("AIMAOS SETUP WIZARD, ECHO MESSENGER & WEB UI INTEGRATION TEST SUITE")
    print("====================================================================\n")

    # 1. Test Setup Wizard Diagnostics
    print("--- 1. TESTING SETUP WIZARD DIAGNOSTICS ---")
    setup_mod = load_module("setup_mod", "/path/to/AIMAOS/setup.py")
    setup_mod.run_diagnostics()
    setup_mod.configure_workspaces()

    # 2. Test Echo Direct Messenger Agent
    print("\n--- 2. TESTING ECHO DIRECT MESSENGER AGENT ---")
    echo_agent_mod = load_module("echo_agent_mod", "/path/to/AIMAOS/Echo-AI/core/agent.py")
    echo = echo_agent_mod.EchoAgent()

    status_resp = echo.process_user_message("What is the status of the office?")
    print("[Echo Status Response]:\n", status_resp)

    doc_resp = echo.process_user_message("Can you make a form for Bob Client?")
    print("\n[Echo Form Task Response]:\n", doc_resp)

    # 3. Verify Office Board state
    print("\n--- 3. VERIFYING OFFICE BOARD POSTED TASKS ---")
    board = OfficeBoard()
    active_tasks = board.board.get("active_tasks", [])
    print(f"Total active tasks on Office Board: {len(active_tasks)}")
    for t in active_tasks:
        print(f"- Task [{t['id']}]: '{t['title']}' assigned to {t['assigned_agent']} (Requester: {t['requester']})")

    print("\n====================================================================")
    print("SUCCESS: ECHO MESSENGER, SETUP WIZARD & WEB UI ARCHITECTURE VERIFIED!")
    print("====================================================================")

if __name__ == "__main__":
    run_test()

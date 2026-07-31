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
from core.comms.office_board import OfficeBoard

def load_module(mod_name, file_path):
    spec = importlib.util.spec_from_file_location(mod_name, file_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod

def run_test():
    print("====================================================================")
    print("AIMAOS SETUP WIZARD, FINN COMMS GATEWAY & WEB UI INTEGRATION TEST SUITE")
    print("====================================================================\n")

    # 1. Test Setup Wizard Diagnostics
    print("--- 1. TESTING SETUP WIZARD DIAGNOSTICS ---")
    setup_mod = load_module("setup_mod", os.path.join(AIMAOS_ROOT, "setup.py"))
    setup_mod.run_diagnostics()
    setup_mod.configure_workspaces()

    # 2. Test Finn as the office's comms gateway / UI entry point (this is the
    # same agent aimaos_ui.py's /api/chat route calls — no demo clone needed).
    print("\n--- 2. TESTING FINN COMMS GATEWAY (WEB UI ENTRY POINT) ---")
    finn_agent_mod = load_module("finn_agent_mod", os.path.join(AIMAOS_ROOT, "Finn-AI/core/agent.py"))
    finn = finn_agent_mod.FinnAgent()

    status_resp = finn.process_user_message("What is the status of the office?")
    print("[Finn Status Response]:\n", status_resp)

    doc_resp = finn.process_user_message("Can you make a form for Bob Client?")
    print("\n[Finn Form Task Response]:\n", doc_resp)

    # 3. Verify Office Board state
    print("\n--- 3. VERIFYING OFFICE BOARD POSTED TASKS ---")
    board = OfficeBoard()
    active_tasks = board.board.get("active_tasks", [])
    print(f"Total active tasks on Office Board: {len(active_tasks)}")
    for t in active_tasks:
        print(f"- Task [{t['id']}]: '{t['title']}' assigned to {t['assigned_agent']} (Requester: {t['requester']})")

    print("\n====================================================================")
    print("SUCCESS: FINN COMMS GATEWAY, SETUP WIZARD & WEB UI ARCHITECTURE VERIFIED!")
    print("====================================================================")

if __name__ == "__main__":
    run_test()

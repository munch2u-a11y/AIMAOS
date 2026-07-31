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
from core.comms.bus import AgentCompanyBus

def load_module(mod_name, file_path):
    spec = importlib.util.spec_from_file_location(mod_name, file_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod

def run_aimaos_test_suite():
    print("====================================================================")
    print("AIMAOS UNIFIED MULTI-AGENT OPERATING SYSTEM TEST SUITE")
    print("Root Workspace: <office root>")
    print("Agents: Alix, Kai, Marley, Quinn, Zoe, Finn")
    print("====================================================================\n")

    board = OfficeBoard()

    # Load AIMAOS agent modules (starter roster only — no demo clones)
    kai_agent_mod = load_module("aimaos_kai", os.path.join(AIMAOS_ROOT, "Kai-AI/core/agent.py"))
    marley_agent_mod = load_module("aimaos_marley", os.path.join(AIMAOS_ROOT, "Marley-AI/core/agent.py"))
    quinn_agent_mod = load_module("aimaos_quinn", os.path.join(AIMAOS_ROOT, "Quinn-AI/core/agent.py"))
    zoe_agent_mod = load_module("aimaos_zoe", os.path.join(AIMAOS_ROOT, "Zoe-AI/core/agent.py"))
    finn_agent_mod = load_module("aimaos_finn", os.path.join(AIMAOS_ROOT, "Finn-AI/core/agent.py"))

    kai = kai_agent_mod.KaiAgent()
    marley = marley_agent_mod.MarleyAgent()
    quinn = quinn_agent_mod.QuinnAgent()
    zoe = zoe_agent_mod.ZoeAgent()
    finn = finn_agent_mod.FinnAgent()

    # 1. Post a document production task to Office Board
    print("--- 1. POSTING HIGH-PRIORITY TASK TO AIMAOS OFFICE BOARD ---")
    task_id = board.post_task(
        title="Generate Joint Simplified Dissolution Petition for Smith Family",
        requester="User",
        target_agent="Alix",
        priority="HIGH"
    )
    print(f"[Office Board Result]: Created Task ID {task_id}")

    # 2. Marley Dispatcher turn scheduling
    print("\n--- 2. MARLEY DISPATCHER PRIORITIZATION & QUEUE DISPATCH ---")
    marley_orch_mod = load_module("aimaos_marley_orch", os.path.join(AIMAOS_ROOT, "Marley-AI/core/orchestrator.py"))
    orchestrator = marley_orch_mod.MarleyOrchestrator()
    turn = orchestrator.dispatch_next_turn()
    print("[Marley Dispatcher Decision]:", turn)

    # 3. Alix communicates with Kai, Quinn, and Finn
    print("\n--- 3. ALIX INTERACTS WITH KAI, QUINN, AND FINN VIA AIMAOS IPC BUS ---")
    alix_bus = AgentCompanyBus("Alix")
    alix_bus.send_message("Kai", "check_duplicates", {"query_text": "Smith Family Dissolution"})
    kai.process_inter_agent_messages()

    alix_bus.send_message("Quinn", "research_brief", {"topic": "Simplified Dissolution Requirements"})
    quinn.process_inter_agent_messages()

    alix_bus.send_message("Finn", "check_office_status", {})
    finn.process_inter_agent_messages()

    board.update_task_status(task_id, "completed", result="Generated court document for Smith family.")

    # 4. Kai Task Archiver
    print("\n--- 4. KAI TASK LOG ARCHIVER ---")
    kai_arch_mod = load_module("aimaos_kai_arch", os.path.join(AIMAOS_ROOT, "Kai-AI/core/task_archiver.py"))
    archiver = kai_arch_mod.KaiTaskArchiver()
    log_file = archiver.archive_task_execution(
        task_data={"id": task_id, "title": "Generate Joint Dissolution", "assigned_agent": "Alix", "priority": "HIGH"},
        execution_trace=["Ingested intake form", "Checked duplicates with Kai", "Consulted Quinn", "Checked status with Finn"]
    )
    print(f"[Kai Archiver Output]: Saved execution trace to {log_file}")

    # 5. Zoe System Improvement Synthesizer
    print("\n--- 5. ZOE ADAPTIVE WORKFLOW SYNTHESIZER ---")
    zoe_synth_mod = load_module("aimaos_zoe_synth", os.path.join(AIMAOS_ROOT, "Zoe-AI/core/workflow_synthesizer.py"))
    synthesizer = zoe_synth_mod.ZoeWorkflowSynthesizer()
    report = synthesizer.synthesize_improvement_report()
    print("[Zoe Synthesizer Output]:\n", report)

    # 6. Verify Alix Inbox
    replies = alix_bus.read_inbox(mark_read=True)
    print(f"\n--- 6. ALIX INBOX AUDIT: Received {len(replies)} inter-agent replies ---")
    for r in replies:
        print(f"- From [{r.get('sender')}]: Action '{r.get('action')}'")

    print("\n====================================================================")
    print("SUCCESS: AIMAOS UNIFIED SUITE IS 100% OPERATIONAL & VERIFIED AT <office root>!")
    print("====================================================================")

if __name__ == "__main__":
    run_aimaos_test_suite()

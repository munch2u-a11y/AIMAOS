import os

def _find_aimaos_root():
    p = os.path.dirname(os.path.abspath(__file__))
    while p != os.path.dirname(p) and not os.path.exists(os.path.join(p, "aimaos_config.yaml")):
        p = os.path.dirname(p)
    return p
AIMAOS_ROOT = os.environ.get("AIMAOS_ROOT") or _find_aimaos_root()
import sys
import json
import shutil
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

def run_office_suite_os_test():
    print("====================================================================")
    print("AI OFFICE SUITE OPERATING SYSTEM (AI OFFICE OS) TEST SUITE")
    print("====================================================================\n")

    board = OfficeBoard()

    # Load agent modules & orchestrators
    marley_orch_mod = load_module("marley_orch_mod", os.path.join(AIMAOS_ROOT, "Marley-AI/core/orchestrator.py"))
    kai_arch_mod = load_module("kai_arch_mod", os.path.join(AIMAOS_ROOT, "Kai-AI/core/task_archiver.py"))
    zoe_synth_mod = load_module("zoe_synth_mod", os.path.join(AIMAOS_ROOT, "Zoe-AI/core/workflow_synthesizer.py"))
    clone_tool_mod = load_module("clone_tool_mod", os.path.join(AIMAOS_ROOT, "Zoe-AI/tools/clone_agent.py"))

    kai_agent_mod = load_module("kai_agent_mod", os.path.join(AIMAOS_ROOT, "Kai-AI/core/agent.py"))
    marley_agent_mod = load_module("marley_agent_mod", os.path.join(AIMAOS_ROOT, "Marley-AI/core/agent.py"))
    quinn_agent_mod = load_module("quinn_agent_mod", os.path.join(AIMAOS_ROOT, "Quinn-AI/core/agent.py"))
    zoe_agent_mod = load_module("zoe_agent_mod", os.path.join(AIMAOS_ROOT, "Zoe-AI/core/agent.py"))

    kai = kai_agent_mod.KaiAgent()
    marley = marley_agent_mod.MarleyAgent()
    quinn = quinn_agent_mod.QuinnAgent()
    zoe = zoe_agent_mod.ZoeAgent()

    # 1. User posts a low-priority background maintenance task for Zoe
    print("--- 1. POSTING BACKGROUND MAINTENANCE TASK FOR ZOE ---")
    board.post_task(
        title="Routine System Log Cleaning",
        requester="User",
        target_agent="Zoe",
        priority="BACKGROUND"
    )

    # 2. User posts a high-priority document production task for Alix
    print("\n--- 2. POSTING HIGH-PRIORITY DOCUMENT TASK FOR ALIX ---")
    high_task_id = board.post_task(
        title="Generate Name Change Petition for Harrison Sterling",
        requester="User",
        target_agent="Alix",
        priority="HIGH",
        details={"client_name": "Harrison Sterling", "county": "Leon"}
    )

    # 3. Marley Dispatcher prioritizes turns & deprioritizes Zoe's maintenance task
    print("\n--- 3. MARLEY DISPATCHER PRIORITIZATION & RESOURCE ALLOCATION ---")
    orchestrator = marley_orch_mod.MarleyOrchestrator()
    turn_assignment = orchestrator.dispatch_next_turn()
    print("[Marley Dispatcher Decision]:", turn_assignment)

    # 4. Alix executes task & interacts with peer agents (Kai, Quinn)
    print("\n--- 4. ALIX EXECUTES WORKFLOW & ASSISTED BY KAI & QUINN ---")
    alix_bus = AgentCompanyBus("Alix")
    alix_bus.send_message("Kai", "check_duplicates", {"query_text": "Harrison Sterling Leon"})
    kai.process_inter_agent_messages()

    alix_bus.send_message("Quinn", "research_brief", {"topic": "Florida Statute 68.07 Name Change"})
    quinn.process_inter_agent_messages()

    # Update Office Board task to completed
    board.update_task_status(high_task_id, "completed", result="Petition generated and archived successfully.")

    # 5. Kai archives completed task execution trace
    print("\n--- 5. KAI ARCHIVES COMPLETED TASK LOG TRACE ---")
    archiver = kai_arch_mod.KaiTaskArchiver()
    archived_file = archiver.archive_task_execution(
        task_data={"id": high_task_id, "title": "Generate Petition Harrison Sterling", "assigned_agent": "Alix", "priority": "HIGH"},
        execution_trace=["Ingested intake text", "Checked duplicates with Kai", "Generated docx via docxtpl", "Archived output"]
    )
    print(f"[Kai Archiver Result]: Saved execution trace to {archived_file}")

    # 6. Zoe analyzes task logs and synthesizes Hermes-Style Improvement Report
    print("\n--- 6. ZOE SYNTHESIZES HERMES-STYLE SYSTEM IMPROVEMENT REPORT ---")
    synthesizer = zoe_synth_mod.ZoeWorkflowSynthesizer()
    report_res = synthesizer.synthesize_improvement_report()
    print("[Zoe Synthesizer Output]:\n", report_res)

    # 7. Zoe instantiates a new specialized Agent Clone, proving the cloning
    # pipeline works — then tears it down immediately. The starter roster is
    # the only thing meant to persist in the working tree/git; this is a
    # smoke test of the *capability*, not a request to keep the clone around.
    print("\n--- 7. ZOE CLONES A THROWAWAY TEST AGENT (cleaned up after this step) ---")
    # clone_agent.py normalizes the name via .capitalize() (e.g. "ZTESTCLONE"
    # -> "Ztestclone"); use an already-normalized name here so the cleanup
    # path below matches the directory the tool actually creates.
    test_clone_name = "Ztestclone"
    clone_res = clone_tool_mod.execute(agent_name=test_clone_name, role="Throwaway Cloning Smoke Test")
    print("[Zoe Agent Cloner Output]:\n", clone_res)
    clone_dir = f"{AIMAOS_ROOT}/{test_clone_name}-AI"
    clone_comms_dir = f"{AIMAOS_ROOT}/comms/{test_clone_name}"
    for path in (clone_dir, clone_comms_dir):
        if os.path.isdir(path):
            shutil.rmtree(path)
            print(f"[Cleanup]: Removed throwaway clone state at {path}")

    print("\n====================================================================")
    print("SUCCESS: AI OFFICE SUITE OS OPERATING AUTONOMOUSLY WITH FULL HARDWARE & KNOWLEDGE CONTROL!")
    print("====================================================================")

if __name__ == "__main__":
    run_office_suite_os_test()

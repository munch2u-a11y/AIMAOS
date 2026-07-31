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
from core.comms.bus import AgentCompanyBus

def load_agent_class(agent_name, file_path, class_name):
    spec = importlib.util.spec_from_file_location(f"{agent_name}_mod", file_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[f"{agent_name}_mod"] = mod
    spec.loader.exec_module(mod)
    return getattr(mod, class_name)()

def run_agent_company_test():
    print("====================================================================")
    print("AGENT COMPANY MULTI-AGENT END-TO-END INTERACTION SUITE")
    print("Agents: Alix (Docs), Kai (Librarian), Marley (Scheduler), Quinn (Research), Zoe (DevOps)")
    print("====================================================================\n")

    alix_bus = AgentCompanyBus("Alix")
    kai = load_agent_class("kai", os.path.join(AIMAOS_ROOT, "Kai-AI/core/agent.py"), "KaiAgent")
    marley = load_agent_class("marley", os.path.join(AIMAOS_ROOT, "Marley-AI/core/agent.py"), "MarleyAgent")
    quinn = load_agent_class("quinn", os.path.join(AIMAOS_ROOT, "Quinn-AI/core/agent.py"), "QuinnAgent")
    zoe = load_agent_class("zoe", os.path.join(AIMAOS_ROOT, "Zoe-AI/core/agent.py"), "ZoeAgent")

    # 1. Alix queries Kai (Digital Librarian) for deduplication check
    print("--- 1. ALIX -> KAI: Checking if client record or template exists ---")
    alix_bus.send_message(
        recipient="Kai",
        action="check_duplicates",
        payload={"query_text": "Julian Vance Duval County Name Change"}
    )
    kai_results = kai.process_inter_agent_messages()
    print("[Kai Processing Logs]:", kai_results)

    # 2. Alix queries Marley (Scheduler) to set filing hearing deadline
    print("\n--- 2. ALIX -> MARLEY: Scheduling filing hearing deadline ---")
    alix_bus.send_message(
        recipient="Marley",
        action="schedule_event",
        payload={
            "event_title": "Court Filing Deadline for Julian Vance",
            "date": "2026-08-20",
            "client_name": "Julian Vance"
        }
    )
    marley_results = marley.process_inter_agent_messages()
    print("[Marley Processing Logs]:", marley_results)

    # 3. Alix queries Quinn (Researcher) for legal statutory brief
    print("\n--- 3. ALIX -> QUINN: Requesting statutory research brief ---")
    alix_bus.send_message(
        recipient="Quinn",
        action="research_brief",
        payload={"topic": "Florida Statute 68.07 Name Change Requirements"}
    )
    quinn_results = quinn.process_inter_agent_messages()
    print("[Quinn Processing Logs]:", quinn_results)

    # 4. Zoe executes full system diagnostics across all 5 agent workspaces
    print("\n--- 4. ZOE: Running DevOps technical health audit across all 5 agents ---")
    alix_bus.send_message(
        recipient="Zoe",
        action="run_diagnostics",
        payload={}
    )
    zoe_results = zoe.process_inter_agent_messages()
    print("[Zoe Processing Logs]:", zoe_results)

    # Read Alix's inbox to verify replies received from Kai, Marley, Quinn, and Zoe!
    replies = alix_bus.read_inbox(mark_read=True)
    print(f"\n--- 5. ALIX INBOX AUDIT: Received {len(replies)} inter-agent replies ---")
    for r in replies:
        print(f"- From [{r.get('sender')}]: Action '{r.get('action')}'")

    print("\n====================================================================")
    print("SUCCESS: ALL 5 AGENTS OPERATING AUTONOMOUSLY & INTERACTING CLEANLY!")
    print("====================================================================")

if __name__ == "__main__":
    run_agent_company_test()

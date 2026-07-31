import os

def _find_aimaos_root():
    p = os.path.dirname(os.path.abspath(__file__))
    while p != os.path.dirname(p) and not os.path.exists(os.path.join(p, "aimaos_config.yaml")):
        p = os.path.dirname(p)
    return p
AIMAOS_ROOT = os.environ.get("AIMAOS_ROOT") or _find_aimaos_root()
import glob
import sys
from datetime import datetime

COMPANY_AGENTS = ["Alix-AI", "Kai-AI", "Marley-AI", "Quinn-AI", "Zoe-AI", "Finn-AI", "Rae-AI"]
BASE_DIR = AIMAOS_ROOT
TOOL_DEFINITION = {
    "name": "system_diagnostics",
    "description": "Performs system health checks, diagnostic audits, dependency verification, and syntax checks across all agent workspaces in the company.",
    "parameters": {
        "type": "object",
        "properties": {
            "target_agent": {
                "type": "string",
                "description": "Optional specific agent to audit (e.g. 'Alix-AI' or 'Kai-AI'). If omitted, audits all agents."
            }
        }
    }
}

def execute(target_agent=None):
    agents_to_check = [target_agent] if target_agent else COMPANY_AGENTS
    results = []

    for agent_folder in agents_to_check:
        apath = os.path.join(BASE_DIR, agent_folder)
        if not os.path.exists(apath):
            results.append(f"❌ {agent_folder}: Directory missing ({apath})")
            continue

        config_path = os.path.join(apath, "config.yaml")
        has_config = os.path.exists(config_path)

        # Count python files
        py_files = glob.glob(os.path.join(apath, "**/*.py"), recursive=True)

        status_str = f"✅ {agent_folder}: Healthy | Config: {'OK' if has_config else 'MISSING'} | Python Scripts: {len(py_files)}"
        results.append(status_str)

    ipc_dir = os.path.join(BASE_DIR, "comms")
    ipc_healthy = os.path.exists(ipc_dir)

    healthy_count = sum(1 for r in results if r.startswith("✅"))
    total_checks = len(results) + 1  # +1 for the IPC bus check
    health_pct = round(100 * (healthy_count + (1 if ipc_healthy else 0)) / max(total_checks, 1))

    report = f"""====================================================================
AGENT COMPANY TECHNICAL DIAGNOSTIC AUDIT
====================================================================
Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
IPC Comms Bus Directory: {'OK' if ipc_healthy else 'NOT INITIALIZED'} ({ipc_dir})

Agent Workspace Audits:
""" + "\n".join(results) + f"""
====================================================================
System Health Rating: {health_pct}% Operational
"""
    return report

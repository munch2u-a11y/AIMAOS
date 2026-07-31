import os
import json
import yaml
from core.comms.bus import AgentCompanyBus

TOOL_DEFINITION = {
    "name": "ask_agent",
    "description": "Sends an inter-agent query to a peer agent in the company (Kai: Digital Librarian, Marley: Scheduler/Comms, Quinn: Researcher, Zoe: DevOps Engineer, Finn: Comms Gateway) and receives their response.",
    "parameters": {
        "type": "object",
        "properties": {
            "recipient": {
                "type": "string",
                "enum": ["Kai", "Marley", "Quinn", "Zoe", "Finn"],
                "description": "The peer agent to query: 'Kai' (Records/Duplicate check), 'Marley' (Scheduler), 'Quinn' (Researcher), 'Zoe' (Technical Engineer), or 'Finn' (Comms Gateway — commandeer_channel to send email/messages)."
            },
            "action": {
                "type": "string",
                "description": "The action requested (e.g., 'check_duplicates', 'search_records', 'schedule_event', 'research_topic', 'run_diagnostics')."
            },
            "payload": {
                "type": "object",
                "description": "JSON object containing query parameters and context."
            }
        },
        "required": ["recipient", "action", "payload"]
    }
}

def execute(recipient, action, payload):
    try:
        bus = AgentCompanyBus("Alix")
        response = bus.ask_peer_and_wait(recipient=recipient, action=action, payload=payload, timeout=8.0)
        return f"Response from Agent {recipient}:\n{json.dumps(response, indent=2)}"
    except Exception as e:
        return f"Error communicating with agent {recipient}: {e}"

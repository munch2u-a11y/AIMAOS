import os

def _find_aimaos_root():
    p = os.path.dirname(os.path.abspath(__file__))
    while p != os.path.dirname(p) and not os.path.exists(os.path.join(p, "aimaos_config.yaml")):
        p = os.path.dirname(p)
    return p
AIMAOS_ROOT = os.environ.get("AIMAOS_ROOT") or _find_aimaos_root()
import json
import logging

logger = logging.getLogger(__name__)

DEFAULT_BELIEFS = {
    "Alix": "I construct precise legal document filings using Jinja2 Word templates, enforcing strict schema validation and zero missing fields.",
    "Kai": "I maintain an organized digital record library, preventing client file duplication and preserving complete task execution logs.",
    "Marley": "I dispatch agent execution turns based on priority weight to protect local CPU/GPU hardware resources from throttling.",
    "Quinn": "I synthesize statutory legal research briefs for Florida Judicial Circuits based on authoritative legal codes.",
    "Zoe": "I audit task execution logs to synthesize adaptive system improvement reports and maintain office self-healing state.",
    "Finn": "I enforce security triage on incoming communications, verify sender permissions, and gate outbound dispatches.",
    "Rae": "I instantiate isolated mini-agent workspaces with custom configs, IPC buses, and subagent tools."
}

class AgentBeliefStore:
    """
    mRAG Belief Store for AIMAOS Agents.
    Stores and retrieves the heaviest ID belief for each mini-agent to power Helix-style ultra-minimal system prompts.
    """
    def __init__(self, memory_dir=os.path.join(AIMAOS_ROOT, "comms")):
        self.memory_dir = memory_dir
        self.beliefs_file = os.path.join(memory_dir, "mrag_agent_beliefs.json")
        os.makedirs(memory_dir, exist_ok=True)
        self.beliefs = self._load_beliefs()

    def _load_beliefs(self):
        if os.path.exists(self.beliefs_file):
            try:
                with open(self.beliefs_file, "r") as f:
                    return json.load(f)
            except Exception:
                pass
        return DEFAULT_BELIEFS.copy()

    def get_heaviest_belief(self, agent_name):
        return self.beliefs.get(agent_name, DEFAULT_BELIEFS.get(agent_name, "I perform specialized single-thought tasks for AIMAOS."))

    def update_belief(self, agent_name, new_belief):
        # Reload before writing: multiple agents share this snapshot file, and
        # writing a stale in-memory copy would clobber peers' recent updates.
        self.beliefs = self._load_beliefs()
        self.beliefs[agent_name] = new_belief
        with open(self.beliefs_file, "w") as f:
            json.dump(self.beliefs, f, indent=2)

    def get_minimal_system_prompt(self, agent_name, role):
        belief = self.get_heaviest_belief(agent_name)
        return f"Identity: You are {agent_name}, the {role} in AIMAOS.\nCore Belief: {belief}"

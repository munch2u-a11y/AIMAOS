import os

def _find_aimaos_root():
    p = os.path.dirname(os.path.abspath(__file__))
    while p != os.path.dirname(p) and not os.path.exists(os.path.join(p, "aimaos_config.yaml")):
        p = os.path.dirname(p)
    return p
AIMAOS_ROOT = os.environ.get("AIMAOS_ROOT") or _find_aimaos_root()
import json
import yaml
from datetime import datetime
from core.security import SecurityValidationError, validate_agent_name

AIMAOS_ROOT = AIMAOS_ROOT
CONFIG_PATH = os.path.join(AIMAOS_ROOT, "aimaos_config.yaml")

TOOL_DEFINITION = {
    "name": "clone_agent",
    "description": "Instantiates a new specialized mini-agent in AIMAOS: a full OfficeAgent workspace with "
                   "its own private belief store, IPC bus, Office Board registration, and starter capabilities. "
                   "Zoe's design_tool_subagent then adds specialist tools.",
    "parameters": {
        "type": "object",
        "properties": {
            "agent_name": {
                "type": "string",
                "description": "Name of the new agent clone (e.g. 'Nova' or 'Echo')."
            },
            "role": {
                "type": "string",
                "description": "Specialized role/title for the agent (e.g. 'Social Media Correspondent')."
            }
        },
        "required": ["agent_name", "role"]
    }
}

def register_in_main_config(clean_name, role, model="qwen3.5:2b"):
    """Integrates the new agent into main aimaos_config.yaml so Marley, Finn, and the UI recognize it."""
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r") as f:
                cfg = yaml.safe_load(f) or {}
            
            if "agents" not in cfg:
                cfg["agents"] = {}
                
            cfg["agents"][clean_name] = {
                "role": role,
                "model": model
            }
            
            with open(CONFIG_PATH, "w") as f:
                yaml.dump(cfg, f, sort_keys=False)
        except Exception as e:
            print(f"Could not register agent in main config: {e}")

def register_in_office_board(clean_name):
    """Initializes IPC inbox queues and Office Board status."""
    inbox_dir = os.path.join(AIMAOS_ROOT, "comms", clean_name, "inbox")
    outbox_dir = os.path.join(AIMAOS_ROOT, "comms", clean_name, "outbox")
    os.makedirs(inbox_dir, exist_ok=True)
    os.makedirs(outbox_dir, exist_ok=True)

    board_path = os.path.join(AIMAOS_ROOT, "comms", "office_board.json")
    if os.path.exists(board_path):
        try:
            with open(board_path, "r") as f:
                data = json.load(f)
            if "agent_statuses" in data:
                data["agent_statuses"][clean_name] = "idle"
            with open(board_path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

def seed_initial_mrag_beliefs(workspace_dir, clean_name, role):
    """Seeds the new agent's private mRAG belief store with office baseline
    rules — through the BeliefStore API, so entries carry the canonical
    schema (`content`, weights, relevance) instead of raw hand-rolled JSON
    that the store cannot read, and re-seeding never clobbers grown beliefs."""
    import sys
    sys.path.insert(0, AIMAOS_ROOT)
    from core.mrag.memory.belief_store import BeliefStore

    mrag_dir = os.path.join(workspace_dir, "workspace", ".memory", "mrag_data")
    store = BeliefStore(data_dir=mrag_dir)
    store.add_belief(
        category="premises", belief_id="seed_identity_premise",
        content=f"I am {clean_name}, the {role} in AIMAOS. I collaborate with peer agents "
                f"via the IPC file bus and Office Board.",
        confidence=0.9, source="clone_seed")
    store.add_belief(
        category="skills", belief_id="seed_skill_browse",
        content="browse_files can list, search, and read approved office storage; "
                "reading before acting beats guessing.",
        confidence=0.8, source="clone_seed")
    store.add_belief(
        category="skills", belief_id="seed_skill_comms",
        content="I communicate with peer agents by posting tasks to the Central Office Board "
                "or dispatching IPC JSON envelopes to their inboxes.",
        confidence=0.8, source="clone_seed")

def execute(agent_name, role):
    try:
        clean_name = validate_agent_name(agent_name)
    except SecurityValidationError as exc:
        return f"Error: {exc}"
    role = (role or "").strip()
    if not role or len(role) > 120 or any(ch in role for ch in "\r\n"):
        return "Error: role must be a single line between 1 and 120 characters."
    role_literal = json.dumps(role)
    workspace_dir = os.path.join(AIMAOS_ROOT, f"{clean_name}-AI")

    if os.path.exists(workspace_dir):
        return f"Error: Workspace for agent '{clean_name}' already exists at {workspace_dir}."

    os.makedirs(os.path.join(workspace_dir, "core"), exist_ok=True)
    os.makedirs(os.path.join(workspace_dir, "tools"), exist_ok=True)
    os.makedirs(os.path.join(workspace_dir, "workspace", ".memory"), exist_ok=True)

    # 1. Private config.yaml
    config_content = {
        "agent": {
            "name": clean_name,
            "role": role,
            "model": "qwen3.5:2b"
        },
        "paths": {
            "memory": f"{workspace_dir}/workspace/.memory"
        }
    }
    with open(os.path.join(workspace_dir, "config.yaml"), "w") as f:
        yaml.dump(config_content, f, sort_keys=False)

    # 2. capabilities.yaml (tool paths are office-root-relative for portability)
    caps = {
        "domains": {
            "file_research": {
                "description": "Explore local directories, search for files, and read documents.",
                "tools": ["shared_tools/browse_files.py"],
            },
        },
        "seed_beliefs": [
            "browse_files can list, search, and read approved office storage; reading before acting beats guessing.",
        ],
    }
    with open(os.path.join(workspace_dir, "capabilities.yaml"), "w") as f:
        yaml.dump(caps, f, sort_keys=False, width=110)

    # 3. core/agent.py (Full OfficeAgent kernel). The generated file carries
    # its own root-finder bootstrap so clones stay portable.
    agent_code = f'''import os
import sys
import logging

def _find_aimaos_root():
    p = os.path.dirname(os.path.abspath(__file__))
    while p != os.path.dirname(p) and not os.path.exists(os.path.join(p, "aimaos_config.yaml")):
        p = os.path.dirname(p)
    return p
AIMAOS_ROOT = os.environ.get("AIMAOS_ROOT") or _find_aimaos_root()
sys.path.insert(0, AIMAOS_ROOT)
from core.office_agent import OfficeAgent

logger = logging.getLogger(__name__)

class {clean_name}Agent(OfficeAgent):
    """Rae-created AIMAOS specialist.
    Rae-cloned mini-agent: evolving belief-based identity, real LLM
    single-thought turns, delegation to specialized tool subagents.
    """
    def __init__(self, config=None):
        super().__init__("{clean_name}", role={role_literal}, config=config)

    def process_user_message(self, message, sender="user", channel="web_ui"):
        """Accepts a direct user message and posts it to the Office Board."""
        task_id = self.board.post_task(
            title=f"[{{channel.upper()}}] Request from {{sender}}",
            requester=sender,
            target_agent=self.name,
            priority="NORMAL",
            details={{"message": message, "channel": channel}}
        )
        self.record_experience(
            f"A user ({{sender}}) sent me a direct request via {{channel}}.",
            category="memory", confidence=0.55)
        return (f"{clean_name} (" + {role_literal} + "): Logged your request to the Office Board "
                f"(Task {{task_id}}). It will be handled in priority order.")
'''
    with open(os.path.join(workspace_dir, "core", "agent.py"), "w") as f:
        f.write(agent_code)

    # 4. Integrate into Main Config, Office Board IPC, & Baseline mRAG Memories
    register_in_main_config(clean_name, role)
    register_in_office_board(clean_name)
    seed_initial_mrag_beliefs(workspace_dir, clean_name, role)

    return (f"Successfully cloned and integrated new AIMAOS agent '{clean_name}'!\n"
            f"- Role: {role}\n"
            f"- Workspace: {workspace_dir}\n"
            f"- Integrated into: main config (aimaos_config.yaml), IPC bus queues (comms/{clean_name}/inbox), & Office Board\n"
            f"- Baseline mRAG beliefs seeded with baseline office IPC principles\n"
            f"- Next: have Zoe design_tool_subagent specialist tools for this role.")

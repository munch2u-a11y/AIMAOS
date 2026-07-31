import os

def _find_aimaos_root():
    p = os.path.dirname(os.path.abspath(__file__))
    while p != os.path.dirname(p) and not os.path.exists(os.path.join(p, "aimaos_config.yaml")):
        p = os.path.dirname(p)
    return p
AIMAOS_ROOT = os.environ.get("AIMAOS_ROOT") or _find_aimaos_root()
import sys
import yaml
import json
import logging

sys.path.insert(0, AIMAOS_ROOT)
sys.path.insert(0, os.path.join(AIMAOS_ROOT, "Alix-AI"))
from core.office_agent import OfficeAgent

logger = logging.getLogger(__name__)


class AlixAgent(OfficeAgent):
    """
    Alix-AI: Document Production & Keeper Agent.
    Helix-style mini-agent: ultra-minimal evolving-belief prompt, real LLM
    single-thought turns, and a private mRAG identity store.
    """
    def __init__(self, config=None):
        super().__init__("Alix", role="Document Production & Keeper Agent", config=config)


class Agent:
    """Interactive CLI agent loop for Alix-AI (used by Alix-AI/main.py)."""
    def __init__(self, config, llm_client, tool_registry):
        from business.memory import ConversationMemory, DocumentProductionMemory
        from core.mrag.memory.belief_store import BeliefStore
        from core.mrag.core.vector_store import DummyVectorStore
        from core.mrag.core.document_digester import DocumentDigester
        from core.mrag.core.pre_generative_injection import PreGenerativeInjector
        from business.watchers.inbox_watcher import InboxWatcher
        from business.subagents.template_reviewer import TemplateReviewer
        self.config = config
        self.llm = llm_client
        self.tools = tool_registry

        # Setup workspace directories
        self.paths = config.get("paths", {})
        self.templates_dir = os.path.abspath(self.paths.get("templates", "./templates"))
        self.skills_dir = os.path.abspath(self.paths.get("skills", "./skills"))
        self.inbox_dir = os.path.abspath(self.paths.get("inbox", "./workspace/inbox"))
        self.output_dir = os.path.abspath(self.paths.get("output", "./workspace/output"))
        self.sessions_dir = os.path.abspath(self.paths.get("sessions", "./workspace/.sessions"))
        self.memory_dir = os.path.abspath(self.paths.get("memory", "./workspace/.memory"))

        for d in [self.templates_dir, self.skills_dir, self.inbox_dir, self.output_dir, self.sessions_dir, self.memory_dir]:
            os.makedirs(d, exist_ok=True)

        self.memory = ConversationMemory(self.sessions_dir)
        self.prod_memory = DocumentProductionMemory(self.memory_dir)

        # Initialize mRAG 2-Layer Memory Engine
        mrag_data_dir = os.path.join(self.memory_dir, "mrag_data")
        self.belief_store = BeliefStore(data_dir=mrag_data_dir)
        self.vector_store = DummyVectorStore()
        self.digester = DocumentDigester(self.belief_store)
        self.mrag_injector = PreGenerativeInjector(
            belief_store=self.belief_store,
            vector_store=self.vector_store,
            max_injected_tokens=800,
        )

        # Initialize Template Reviewer Subagent
        self.template_reviewer = TemplateReviewer(
            templates_dir=self.templates_dir,
            memory_dir=self.memory_dir,
            llm_client=self.llm
        )

        # Initialize InboxWatcher background daemon
        downloads_dir = os.path.expanduser("~/Downloads")
        watch_targets = [self.inbox_dir]
        if os.path.exists(downloads_dir):
            watch_targets.append(downloads_dir)

        self.watcher = InboxWatcher(
            watch_dirs=watch_targets,
            document_digester=self.digester,
            poll_interval=5.0
        )
        self.watcher.start()

    def _get_dynamic_context(self):
        """Discovers existing templates and skills to inject into the system prompt."""
        templates = []
        if os.path.exists(self.templates_dir):
            for item in os.listdir(self.templates_dir):
                item_path = os.path.join(self.templates_dir, item)
                if os.path.isdir(item_path):
                    yaml_path = os.path.join(item_path, "template.yaml")
                    if os.path.exists(yaml_path):
                        try:
                            with open(yaml_path, "r") as f:
                                meta = yaml.safe_load(f)
                                templates.append(f"- ID/Folder: {item}\n  Name: {meta.get('name')}\n  Description: {meta.get('description')}")
                        except Exception:
                            templates.append(f"- Folder: {item}")
                    else:
                        templates.append(f"- Folder: {item}")
                elif item.endswith(".docx"):
                    templates.append(f"- Document file: {item}")

        skills = []
        if os.path.exists(self.skills_dir):
            for item in os.listdir(self.skills_dir):
                item_path = os.path.join(self.skills_dir, item)
                if os.path.isdir(item_path):
                    yaml_path = os.path.join(item_path, "skill.yaml")
                    if os.path.exists(yaml_path):
                        try:
                            with open(yaml_path, "r") as f:
                                meta = yaml.safe_load(f)
                                skills.append(f"- Name: {meta.get('name')}\n  Description: {meta.get('description')}")
                        except Exception:
                            skills.append(f"- Folder: {item}")
                    else:
                        skills.append(f"- Folder: {item}")

        templates_str = "\n".join(templates) if templates else "None available yet."
        skills_str = "\n".join(skills) if skills else "None available yet."

        return templates_str, skills_str

    def _get_system_prompt(self, user_query=""):
        templates_str, skills_str = self._get_dynamic_context()
        memory_summary = self.prod_memory.get_system_prompt_summary()

        mrag_context = ""
        try:
            self.mrag_injector.sync_index()
            mrag_injection = self.mrag_injector.inject(trigger_text=user_query)
            if mrag_injection and mrag_injection.strip():
                mrag_context = f"\n[mRAG VERBATIM & BELIEF CONTEXT]\n{mrag_injection.strip()}\n"
        except Exception as e:
            logger.warning(f"Failed to build mRAG injection: {e}")

        return f"""You are Alix-AI, a local document maker, keeper, and pipeline agent powered by integrated mRAG memory and specialized subagents.
Your primary goal is to help users automate document intake, information extraction, template selection, form population, and client dispatch.

You operate in a fully local workspace:
- Inbox directory: {self.inbox_dir} (Where input files/forms are dropped)
- Output directory: {self.output_dir} (Where final rendered documents go)
- Templates directory: {self.templates_dir} (Self-built template library)
- Skills directory: {self.skills_dir} (Automation scripts)

SPECIALIZED SUBAGENTS:
- Template Reviewer Subagent: Performs background auditing and cleaning of templates in small, token-optimized paragraph chunks. Use the review_templates tool to trigger reviews or queue notes.

AVAILABLE TEMPLATES IN LIBRARY:
{templates_str}

AVAILABLE AUTOMATION SKILLS:
{skills_str}

{memory_summary}
{mrag_context}
CORE OPERATIONAL INSTRUCTIONS:
1. When asked to create or populate a form/document for a client:
   a) Inspect client facts from conversation, mRAG memory, or intake files using search_files or ingest_document.
   b) Select the matching template from the template library using list_files or inspect_template.
   c) Use populate_template to fill the template and render .docx/.pdf.
   d) Use dispatch_document to archive the completed file into workspace/output/<client_name>/<date>/.
2. If a template has formatting issues or missing field mappings, use review_templates to trigger background subagent reviews.
3. All operations run locally. Summarize exact steps taken and provide clickable file links to generated output files.
"""

    def process_input(self, user_input, console_callback=None):
        """Runs the agent loop for a single user interaction."""
        if console_callback is None:
            def console_callback(event_type, data):
                pass

        try:
            from datetime import datetime
            self.belief_store.merge_or_add_belief(
                category="premises",
                belief_id=f"user_request_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}",
                content=f"User request: {user_input}",
                confidence=0.5,
                source="alix_cli",
                vector_store=self.vector_store,
            )
        except Exception:
            pass

        self.memory.add_message("user", user_input)

        max_turns = 10
        turn = 0

        while turn < max_turns:
            system_prompt = self._get_system_prompt(user_query=user_input)
            messages = [{"role": "system", "content": system_prompt}]
            messages.extend(self.memory.get_messages())

            console_callback("agent_start_thinking", {"turn": turn + 1})

            try:
                response = self.llm.chat(messages, tools=self.tools.get_tool_definitions())
            except Exception as e:
                error_msg = f"LLM error: {e}"
                console_callback("agent_error", {"message": error_msg})
                self.memory.add_message("assistant", error_msg)
                return error_msg

            if response.content:
                console_callback("agent_message", {"content": response.content})

            if response.tool_calls:
                self.memory.add_message("assistant", response.content, tool_calls=response.tool_calls)

                for tc in response.tool_calls:
                    name = tc["name"]
                    args = tc["arguments"]
                    tc_id = tc["id"]

                    console_callback("tool_start", {"name": name, "arguments": args})
                    result = self.tools.execute_tool(name, args)
                    console_callback("tool_end", {"name": name, "result": result})

                    self.memory.add_message(role="tool", content=result, name=name, tool_call_id=tc_id)

                turn += 1
                continue
            else:
                self.memory.add_message("assistant", response.content)
                return response.content

        limit_msg = "Agent loop execution limit reached (max 10 turns)."
        console_callback("agent_error", {"message": limit_msg})
        self.memory.add_message("assistant", limit_msg)
        return limit_msg

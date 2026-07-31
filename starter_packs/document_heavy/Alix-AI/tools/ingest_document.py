import os
import yaml
from core.mrag.memory.belief_store import BeliefStore
from core.mrag.core.memory_ingestor import MemoryIngestor

TOOL_DEFINITION = {
    "name": "ingest_document",
    "description": "Digests an intake file (PDF, DOCX, TXT, MD, JSON) into mRAG Layer 1 verbatim memory for fast instant retrieval and client info matching.",
    "parameters": {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Absolute or relative path to the intake document file."
            },
            "client_name": {
                "type": "string",
                "description": "Optional client name to associate with this intake document."
            }
        },
        "required": ["file_path"]
    }
}

def get_config():
    tools_dir = os.path.dirname(os.path.abspath(__file__))
    project_dir = os.path.dirname(tools_dir)
    config_path = os.path.join(project_dir, "config.yaml")
    if os.path.exists(config_path):
        with open(config_path, "r") as f:
            try:
                return yaml.safe_load(f)
            except Exception:
                pass
    return {}

def execute(file_path, client_name=None):
    abs_path = os.path.abspath(file_path)
    if not os.path.exists(abs_path):
        return f"Error: File not found at {abs_path}"

    config = get_config()
    paths = config.get("paths", {})
    memory_dir = os.path.abspath(paths.get("memory", "./workspace/.memory"))

    try:
        # Read text content
        if abs_path.endswith(".docx"):
            import docx
            doc = docx.Document(abs_path)
            text = "\n".join(p.text for p in doc.paragraphs)
        else:
            with open(abs_path, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()

        mrag_data_dir = os.path.join(memory_dir, "mrag_data")
        os.makedirs(mrag_data_dir, exist_ok=True)

        belief_store = BeliefStore(data_dir=mrag_data_dir)
        ingestor = MemoryIngestor(belief_store)
        chunk_ids = ingestor.add_event(text=text, source=abs_path)
        chunks_created = len(chunk_ids or [])

        # If client_name provided, store client association belief gracefully
        if client_name:
            try:
                belief_store.add_belief(
                    category="people",
                    template=f"{client_name} intake document ingested from {os.path.basename(abs_path)}."
                )
            except Exception:
                pass

        return f"Success: Ingested '{os.path.basename(abs_path)}' into mRAG Layer 1 memory ({chunks_created} verbatim chunks indexed)."
    except Exception as e:
        return f"Error ingesting document '{file_path}': {e}"

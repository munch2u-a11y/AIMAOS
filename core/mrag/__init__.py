import sys
import os

mrag_dir = os.path.dirname(os.path.abspath(__file__))
if "mrag" not in sys.modules:
    import importlib.util
    spec = importlib.util.spec_from_file_location("mrag", os.path.join(mrag_dir, "__init__.py"), submodule_search_locations=[mrag_dir])
    if spec and spec.loader:
        mrag_mod = importlib.util.module_from_spec(spec)
        sys.modules["mrag"] = mrag_mod

from mrag.core.pre_generative_injection import PreGenerativeInjector
from mrag.core.context_compressor import ContextCompressor
from mrag.core.belief_consolidator import BeliefConsolidator
from mrag.core.memory_ingestor import MemoryIngestor
from mrag.core.document_digester import DocumentDigester
from mrag.core.local_profile import LocalAgentProfile
from mrag.core.journal import JournalWriter
from mrag.adapters.llm_detector import LocalLLM, detect_local_llm
from mrag.adapters.tool_groups import Tool, ToolGroup, CompositeToolGroup, ToolGroupRegistry, SubAgentToolRunner
from mrag.adapters.starter_tools import build_starter_registry
from mrag.adapters.scheduler import ScheduleStore, build_schedule_group
from mrag.adapters.dashboard import MemoryDashboard
from mrag.adapters.tool_knowledge import ToolKnowledgeConsolidator
from mrag.adapters.tool_orchestrator import ToolOrchestrator
from mrag.adapters.pulse_loop import PulseConfig, PulseLoop
from mrag.adapters.pulse_hooks import (
    ControlState, PulseHook, PulseRecord, StabilityHook, ToolReflexHook,
    ConceptFlowHook, default_hooks,
)
from mrag.adapters.telegram_comms import OutboundGovernor, TelegramComms, build_telegram_group
from mrag.core.vector_store import VectorStore, ChromaVectorStore, PineconeVectorStore, DummyVectorStore, create_vector_store, OllamaEmbeddingFunction
from mrag.memory.belief_store import BeliefStore
from mrag import adapters

__all__ = [
    "PreGenerativeInjector",
    "ContextCompressor",
    "BeliefConsolidator",
    "MemoryIngestor",
    "DocumentDigester",
    "LocalAgentProfile",
    "LocalLLM",
    "detect_local_llm",
    "Tool",
    "ToolGroup",
    "CompositeToolGroup",
    "ToolGroupRegistry",
    "build_starter_registry",
    "ScheduleStore",
    "build_schedule_group",
    "SubAgentToolRunner",
    "MemoryDashboard",
    "ToolKnowledgeConsolidator",
    "ToolOrchestrator",
    "PulseConfig",
    "PulseLoop",
    "ControlState",
    "PulseHook",
    "PulseRecord",
    "StabilityHook",
    "ToolReflexHook",
    "ConceptFlowHook",
    "default_hooks",
    "OutboundGovernor",
    "TelegramComms",
    "build_telegram_group",
    "JournalWriter",
    "VectorStore",
    "ChromaVectorStore",
    "PineconeVectorStore",
    "DummyVectorStore",
    "create_vector_store",
    "OllamaEmbeddingFunction",
    "BeliefStore",
    "adapters"
]

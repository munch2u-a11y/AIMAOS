import os

def _find_aimaos_root():
    p = os.path.dirname(os.path.abspath(__file__))
    while p != os.path.dirname(p) and not os.path.exists(os.path.join(p, "aimaos_config.yaml")):
        p = os.path.dirname(p)
    return p
AIMAOS_ROOT = os.environ.get("AIMAOS_ROOT") or _find_aimaos_root()
import sys
import logging

sys.path.insert(0, AIMAOS_ROOT)
from core.office_agent import OfficeAgent

logger = logging.getLogger(__name__)


class QuinnAgent(OfficeAgent):
    """Quinn-AI: Research & Legal Intelligence Reporter.
    Helix-style mini-agent: ultra-minimal evolving-belief prompt, real LLM
    single-thought turns, and a private mRAG identity store.
    """
    def __init__(self, config=None):
        super().__init__("Quinn", role="Research & Legal Intelligence Reporter", config=config)

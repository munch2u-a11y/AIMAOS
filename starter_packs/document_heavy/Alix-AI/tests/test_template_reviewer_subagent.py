import os

def _find_aimaos_root():
    p = os.path.dirname(os.path.abspath(__file__))
    while p != os.path.dirname(p) and not os.path.exists(os.path.join(p, "aimaos_config.yaml")):
        p = os.path.dirname(p)
    return p
AIMAOS_ROOT = os.environ.get("AIMAOS_ROOT") or _find_aimaos_root()
import sys

sys.path.insert(0, AIMAOS_ROOT)
sys.path.insert(0, os.path.join(AIMAOS_ROOT, "Alix-AI"))
from business.subagents.template_reviewer import TemplateReviewer
from core.tools import ToolRegistry

def test_subagent():
    print("=== TESTING TEMPLATE REVIEWER SUBAGENT (TOKEN-OPTIMIZED CHUNKS) ===")

    reviewer = TemplateReviewer(
        templates_dir=os.path.join(AIMAOS_ROOT, "Alix-AI/templates"),
        memory_dir=os.path.join(AIMAOS_ROOT, "Alix-AI/workspace/.memory")
    )

    # 1. Queue a review note for form_12_982_a
    note_msg = reviewer.add_review_note(
        template_name="form_12_982_a",
        note="Review form headers, clear footers, and ensure client_email field is indexed."
    )
    print("\n[QUEUE NOTE RESULT]:", note_msg)

    # 2. Process pending notes via tool registry
    registry = ToolRegistry(os.path.join(AIMAOS_ROOT, "Alix-AI/tools"))
    tool_res = registry.execute_tool("review_templates", {
        "action": "process_pending"
    })
    print("\n[SUBAGENT BATCH EXECUTION OUTPUT]:\n", tool_res)

    # 3. Direct single template review test on form_12_982_b
    single_res = registry.execute_tool("review_templates", {
        "template_name": "form_12_982_b",
        "action": "review_single",
        "note": "Token-optimized chunk review test"
    })
    print("\n[SINGLE TEMPLATE REVIEW OUTPUT]:\n", single_res)

if __name__ == "__main__":
    test_subagent()

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
from collections import Counter
from datetime import datetime

spec = importlib.util.spec_from_file_location("kai_task_archiver_mod", os.path.join(AIMAOS_ROOT, "Kai-AI/core/task_archiver.py"))
kai_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kai_mod)
KaiTaskArchiver = kai_mod.KaiTaskArchiver

REPORTS_DIR = os.path.join(AIMAOS_ROOT, "Zoe-AI/workspace/diagnostics")
OFFICE_BOARD_FILE = os.path.join(AIMAOS_ROOT, "comms/office_board.json")


class ZoeWorkflowSynthesizer:
    """
    Zoe Adaptive Workflow Synthesizer.
    Computes System Improvement & Skill Reports from the office's ACTUAL
    records: Kai's archived traces plus the live Office Board. Every metric
    in the report is derived from data — nothing is hardcoded.
    """
    def __init__(self):
        self.archiver = KaiTaskArchiver()
        os.makedirs(REPORTS_DIR, exist_ok=True)

    def _load_board(self):
        try:
            with open(OFFICE_BOARD_FILE) as f:
                return json.load(f)
        except Exception:
            return {}

    def _narrative(self, stats):
        """Optional LLM narrative over the computed stats (Zoe's own voice).
        Returns '' when the local model is unreachable — metrics stand alone."""
        try:
            sys.path.insert(0, AIMAOS_ROOT)
            from core.llm import LLMClient
            from core.office_agent import load_office_config
            office_cfg = load_office_config()
            llm_cfg = dict(office_cfg.get("llm", {}))
            llm_cfg["model"] = (office_cfg.get("agents", {}).get("Zoe", {}).get("model")
                               or llm_cfg.get("default_model", "qwen3.5:2b"))
            client = LLMClient({"llm": llm_cfg})
            resp = client.chat([
                {"role": "system",
                 "content": "You are Zoe, the DevOps Maintenance Engineer in AIMAOS. "
                            "You write brief, blunt operational assessments."},
                {"role": "user",
                 "content": "Office metrics (computed from real records):\n"
                            f"{json.dumps(stats, indent=2)}\n\n"
                            "Write 3-5 bullet points: what is working, what is the biggest "
                            "operational risk, and one concrete improvement. No preamble."},
            ])
            return (resp.content or "").strip()
        except Exception:
            return ""

    def synthesize_improvement_report(self):
        """Analyzes archived task logs + live board and compiles a data-driven report."""
        logs = self.archiver.get_all_archived_logs()
        board = self._load_board()
        active = board.get("active_tasks", [])
        completed_board = board.get("completed_tasks", [])

        if not logs and not completed_board and not active:
            return "No task records available for analysis yet."

        # --- Metrics computed from actual records
        agent_load = Counter(t.get("assigned_agent") for t in completed_board if t.get("assigned_agent"))
        agent_load.update(l.get("assigned_agent") for l in logs if l.get("assigned_agent"))
        priorities = Counter((t.get("priority") or "UNKNOWN") for t in completed_board)

        abandoned = [t for t in completed_board
                     if str(t.get("result", "")).startswith("ABANDONED")]
        failed_active = [t for t in active if t.get("status") == "failed"]
        stuck_in_progress = [t for t in active if t.get("status") == "in_progress"]
        queued = [t for t in active if t.get("status") == "queued"]

        total_finished = len(completed_board)
        genuinely_completed = total_finished - len(abandoned)
        denominator = total_finished + len(failed_active)
        efficiency = round(100 * genuinely_completed / denominator) if denominator else None

        stats = {
            "archived_traces": len(logs),
            "board_completed_tasks": total_finished,
            "abandoned_tasks": len(abandoned),
            "failed_awaiting_retry": len(failed_active),
            "in_progress": len(stuck_in_progress),
            "queued_backlog": len(queued),
            "operational_efficiency_pct": efficiency,
            "busiest_agents": dict(agent_load.most_common(5)),
            "priority_mix_of_completed": dict(priorities),
        }

        narrative = self._narrative(stats)

        report_id = f"diagnostic_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        report_path = os.path.join(REPORTS_DIR, report_id)

        lines = [
            "# System Improvement & Skill Report",
            f"*Generated*: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} by **Zoe (DevOps Engineer & Synthesizer)**",
            "",
            "## Operational Analytics (computed from live records)",
            f"- **Archived Execution Traces (Kai)**: {stats['archived_traces']}",
            f"- **Completed Tasks on Board**: {stats['board_completed_tasks']} "
            f"({stats['abandoned_tasks']} abandoned after retries)",
            f"- **Failures Awaiting Retry**: {stats['failed_awaiting_retry']} | "
            f"**In Progress**: {stats['in_progress']} | **Queued Backlog**: {stats['queued_backlog']}",
            f"- **Operational Efficiency Index**: "
            + (f"{efficiency}% (genuine completions / all finished+failed)" if efficiency is not None else "N/A (no finished work yet)"),
            f"- **Busiest Agents**: " + (", ".join(f"{a} ({n})" for a, n in stats["busiest_agents"].items()) or "none"),
            f"- **Priority Mix of Completed Work**: "
            + (", ".join(f"{p}: {n}" for p, n in stats["priority_mix_of_completed"].items()) or "none"),
        ]
        if abandoned:
            lines += ["", "## Abandoned Task Audit"]
            lines += [f"- '{t.get('title')}' — {str(t.get('result'))[:160]}" for t in abandoned[:5]]
        if narrative:
            lines += ["", "## Zoe's Assessment", narrative]

        with open(report_path, "w") as f:
            f.write("\n".join(lines) + "\n")

        return (f"Synthesized system improvement report from {len(logs)} traces "
                f"and {len(active) + total_finished} board records.\n"
                f"- Saved Report: {report_path}\n"
                f"- Efficiency Index: {efficiency if efficiency is not None else 'N/A'}%")

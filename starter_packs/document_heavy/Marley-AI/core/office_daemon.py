"""
Marley's Office Daemon — the autonomous pulse loop of AIMAOS.

Marley owns the schedule: every cycle, Marley decides which agent takes the
next turn (priority-weighted with aging), runs that agent's real
single-thought LLM turn, keeps every inbox flowing, requeues expired or
failed work, and rotates background identity reflections so each agent's
beliefs keep evolving from its actual experiences.

Run it:
    python <office root>/run_office.py
    (flags: --max-cycles N for bounded runs, --poll SECONDS to override cadence)

One turn executes at a time — Marley's charter is protecting local CPU/GPU
from concurrent model load thrash.
"""
import os

def _find_aimaos_root():
    p = os.path.dirname(os.path.abspath(__file__))
    while p != os.path.dirname(p) and not os.path.exists(os.path.join(p, "aimaos_config.yaml")):
        p = os.path.dirname(p)
    return p
AIMAOS_ROOT = os.environ.get("AIMAOS_ROOT") or _find_aimaos_root()
import sys
import json
import time
import signal
import logging
import importlib.util
from datetime import datetime, timedelta

AIMAOS_ROOT = AIMAOS_ROOT
sys.path.insert(0, AIMAOS_ROOT)

from core.comms.office_board import OfficeBoard
from core.office_agent import load_office_config

logger = logging.getLogger("aimaos.office_daemon")
DAEMON_STATUS_PATH = os.path.join(AIMAOS_ROOT, "comms", "daemon_status.json")


def write_daemon_status(state, *, cycle=0, current_task=None, error=None):
    """Publish an atomic, content-free daemon heartbeat for the dashboard."""
    os.makedirs(os.path.dirname(DAEMON_STATUS_PATH), exist_ok=True)
    payload = {
        "state": state,
        "pid": os.getpid(),
        "cycle": cycle,
        "current_task": current_task,
        "error": str(error)[:1000] if error else None,
        "last_heartbeat": datetime.now().isoformat(),
    }
    temp_path = DAEMON_STATUS_PATH + f".{os.getpid()}.tmp"
    with open(temp_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
    os.replace(temp_path, DAEMON_STATUS_PATH)

# Preferred clock-in order only — never a requirement. Which agents actually
# exist depends on the starter pack the operator set up plus any Rae-cloned
# specialists, so the roster is discovered from the filesystem.
PREFERRED_ORDER = ["Marley", "Alix", "Kai", "Quinn", "Zoe", "Finn", "Rae"]


def discover_roster():
    """Every materialized agent workspace, so a different starter pack or a
    newly cloned specialist is hired automatically on the next daemon start."""
    found = sorted(entry[:-3] for entry in os.listdir(AIMAOS_ROOT)
                   if entry.endswith("-AI")
                   and os.path.exists(os.path.join(AIMAOS_ROOT, entry, "core", "agent.py")))
    return sorted(found, key=lambda n: (PREFERRED_ORDER.index(n)
                                        if n in PREFERRED_ORDER else len(PREFERRED_ORDER), n))


AGENT_CLASSES = {}


def load_agent(name):
    path = os.path.join(AIMAOS_ROOT, f"{name}-AI", "core", "agent.py")
    spec = importlib.util.spec_from_file_location(f"aimaos_daemon_{name.lower()}", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return getattr(mod, f"{name}Agent")()


class OfficeDaemon:
    def __init__(self, poll_interval=None):
        full_cfg = load_office_config()
        cfg = full_cfg.get("office", {})
        workflow_cfg = full_cfg.get("workflow", {})
        self.poll_interval = poll_interval if poll_interval is not None else float(cfg.get("poll_interval_sec", 3.0))
        self.task_lease_sec = int(cfg.get("task_lease_sec", 600))
        self.max_task_retries = int(cfg.get("max_task_retries", 2))
        self.reflection_every = int(cfg.get("reflection_every_cycles", 12))
        self.idle_backoff_max_sec = float(cfg.get("idle_backoff_max_sec", 60.0))
        self.workflow_review_interval_sec = max(
            60.0, float(workflow_cfg.get("review_check_interval_sec", 300.0))
        )
        self._last_workflow_review_check = 0.0
        self._consecutive_idle_cycles = 0

        self.board = OfficeBoard()
        print("[Office Daemon] Hiring the roster...")
        self.agents = {}
        for name in discover_roster():
            try:
                self.agents[name] = load_agent(name)
                print(f"  • {name} clocked in (model: {self.agents[name].model})")
            except Exception as e:
                print(f"  • {name} FAILED to clock in: {e}")
        self.marley = self.agents.get("Marley")
        self.cycle = 0
        self._reflection_rotation = 0
        self._running = True
        try:
            from core.privacy import prune_runtime_records
            print(f"[Office Daemon] Privacy housekeeping: {prune_runtime_records(AIMAOS_ROOT)}")
        except Exception as exc:
            logger.warning("Privacy housekeeping failed: %s", exc)
        self.maybe_run_advancement_review()
        write_daemon_status("starting", cycle=self.cycle)

    def maybe_run_advancement_review(self, *, force=False):
        """Run Marley's deterministic blocker/reminder review once per day."""
        now = time.monotonic()
        if not force and now - self._last_workflow_review_check < self.workflow_review_interval_sec:
            return None
        self._last_workflow_review_check = now
        try:
            from core.workflow_review import run_daily_advancement_review
            report = run_daily_advancement_review(force=force, board=self.board)
            if report.get("ran"):
                print(f"[Office Daemon] Daily advancement review: {report}")
            return report
        except Exception as exc:
            logger.warning("Daily advancement review failed: %s", exc)
            return {"ran": False, "reason": "error"}

    # ------------------------------------------------------------ hygiene
    def requeue_expired_and_failed(self):
        """Marley's board hygiene: requeue leases that expired and failed
        tasks with retries left; abandon tasks that exhausted retries."""
        self.board.board = self.board._load_board()
        now = datetime.now()
        for t in list(self.board.board.get("active_tasks", [])):
            status = t.get("status")
            if status == "in_progress":
                dispatched = t.get("dispatched_at")
                try:
                    age = (now - datetime.fromisoformat(dispatched)).total_seconds() if dispatched else None
                except Exception:
                    age = None
                if age is not None and age > self.task_lease_sec:
                    self.board.update_task_status(t["id"], "queued")
                    self.board.log_activity(
                        f"[MARLEY DAEMON] Lease expired on '{t['title']}' after {int(age)}s; requeued.")
            elif status == "failed":
                if int(t.get("retries", 0)) <= self.max_task_retries:
                    self.board.update_task_status(t["id"], "queued")
                    self.board.log_activity(
                        f"[MARLEY DAEMON] Requeued failed task '{t['title']}' "
                        f"(retry {t.get('retries', 0)}/{self.max_task_retries}).")
                else:
                    self.board.update_task_status(t["id"], "completed",
                                                  result=f"ABANDONED after {t.get('retries')} failed attempts: "
                                                         f"{t.get('result', 'no error recorded')}")
                    self.board.log_activity(
                        f"[MARLEY DAEMON] Abandoned task '{t['title']}' after exhausting retries.")

    HOUSEKEEPING_COOLDOWN_SEC = 300

    def maybe_post_housekeeping_task(self):
        """Idle-cycle housekeeping: keeps exactly one pending 'review stale
        cases' task on the board for Kai at a time, so its list_stale/review
        workflow actually runs via real turns instead of staying a belief
        Kai never gets a task to act on. BACKGROUND priority -- this never
        preempts real client work, only fills genuinely idle cycles.

        Cooldown-gated: without this, completing one housekeeping pass makes
        the very next idle check post another immediately, so a quiet office
        never actually goes idle -- it just churns the same 'nothing stale'
        result over and over instead of napping (observed directly: a real
        40-cycle run spent 32 cycles on this ping-pong once real work ran
        out). Only re-post once the last one has been done for a while."""
        if "Kai" not in self.agents:
            return
        self.board.board = self.board._load_board()
        existing = [t for t in self.board.board.get("active_tasks", [])
                   if t.get("title") == "Housekeeping: review stale cases"
                   and t.get("status") in ("queued", "in_progress")]
        if existing:
            return
        recent_done = [t for t in self.board.board.get("completed_tasks", [])
                       if t.get("title") == "Housekeeping: review stale cases" and t.get("completed_at")]
        if recent_done:
            last = max(t["completed_at"] for t in recent_done)
            try:
                age = (datetime.now() - datetime.fromisoformat(last)).total_seconds()
            except Exception:
                age = None
            if age is not None and age < self.HOUSEKEEPING_COOLDOWN_SEC:
                return
        self.board.post_task(
            title="Housekeeping: review stale cases",
            requester="Marley",
            target_agent="Kai",
            priority="BACKGROUND",
            details={"instruction": "Call manage_case_records action=list_stale, then action=review "
                                    "for whatever it reports."},
        )

    def process_all_inboxes(self):
        for name, agent in self.agents.items():
            try:
                results = agent.process_inter_agent_messages()
                for r in results:
                    print(f"    [{name} inbox] {r}")
            except Exception as e:
                logger.warning(f"[{name}] inbox processing failed: {e}")

    # ------------------------------------------------------------ the pulse
    def _fallback_dispatch(self):
        """Priority dispatch when the office has no scheduler agent (a starter
        pack without Marley). Same contract as MarleyOrchestrator.dispatch_next_turn
        so the pulse loop doesn't care which one ran."""
        weights = {"CRITICAL": 0, "HIGH": 1, "NORMAL": 2, "BACKGROUND": 3}
        self.board.board = self.board._load_board()
        queued = [t for t in self.board.board.get("active_tasks", [])
                  if t.get("status") == "queued"]
        if not queued:
            return "No queued tasks on the Office Board. Office is idle."
        top = sorted(queued, key=lambda t: weights.get(t.get("priority", "NORMAL"), 99))[0]
        self.board.update_task_status(top["id"], "in_progress")
        self.board.update_agent_status(top["assigned_agent"], "working")
        return {
            "task_id": top["id"],
            "assigned_agent": top["assigned_agent"],
            "priority": top.get("priority", "NORMAL"),
            "title": top.get("title", "Untitled task"),
            "status": "in_progress",
        }

    def run_cycle(self):
        """One office pulse: hygiene -> inboxes -> Marley dispatch -> the
        assigned agent's real turn -> periodic identity reflection."""
        self.cycle += 1
        write_daemon_status("polling", cycle=self.cycle)
        print(f"\n--- OFFICE PULSE {self.cycle} [{datetime.now().strftime('%H:%M:%S')}] ---")

        self.maybe_run_advancement_review()
        self.requeue_expired_and_failed()
        self.process_all_inboxes()

        turn = (self.marley.dispatch_next_turn() if self.marley
                else self._fallback_dispatch())
        if isinstance(turn, dict):
            agent_name = turn["assigned_agent"]
            agent = self.agents.get(agent_name)
            print(f"  [Marley] Turn -> {agent_name}: '{turn['title']}' (priority {turn['priority']})")
            write_daemon_status("working", cycle=self.cycle, current_task={
                "id": turn.get("task_id"), "title": turn.get("title"), "agent": agent_name,
            })
            if agent is None:
                # Task addressed to a clone/unknown agent Marley didn't hire.
                self.board.update_task_status(turn["task_id"], "failed",
                                              result=f"No active agent named '{agent_name}' in the office roster.")
                print(f"  [Daemon] No roster agent '{agent_name}'; task marked failed for requeue/abandon.")
            else:
                result = agent.execute_single_turn(task_id=turn["task_id"])
                preview = str(result).replace("\n", " ")[:220]
                print(f"  [{agent_name}] {preview}")
            self._consecutive_idle_cycles = 0
        else:
            print(f"  [Marley] {turn}")
            # Idle office: make sure Kai has a standing reason to do its
            # housekeeping pass. Real identity reflection stays on its normal
            # periodic cadence below rather than firing every idle pulse --
            # otherwise a long quiet stretch burns a real LLM call every few
            # seconds for no new experience to reflect on.
            self.maybe_post_housekeeping_task()
            self._consecutive_idle_cycles += 1

        if self.reflection_every and self.cycle % self.reflection_every == 0:
            self.run_reflection_turn()
        write_daemon_status("idle" if self._consecutive_idle_cycles else "ready", cycle=self.cycle)

    def _next_sleep_interval(self):
        """Real work keeps the office on its normal pulse. An idle office
        naps progressively longer (doubling each consecutive idle cycle,
        capped) instead of spinning at the same tight interval forever with
        nothing to do -- any new task snaps it back to full pulse rate
        immediately, since a busy cycle resets the idle counter to 0."""
        if self._consecutive_idle_cycles <= 0:
            return self.poll_interval
        backoff = self.poll_interval * (2 ** min(self._consecutive_idle_cycles, 10))
        return min(backoff, self.idle_backoff_max_sec)

    def run_reflection_turn(self):
        names = list(self.agents)
        if not names:
            return
        name = names[self._reflection_rotation % len(names)]
        self._reflection_rotation += 1
        agent = self.agents.get(name)
        if not agent or not hasattr(agent, "reflect"):
            return
        try:
            print(f"  [Reflection] {agent.reflect()}")
        except Exception as e:
            logger.warning(f"[{name}] reflection failed: {e}")

    def is_pause_requested(self) -> bool:
        control_path = os.path.join(AIMAOS_ROOT, "comms", "daemon_control.json")
        try:
            with open(control_path, "r", encoding="utf-8") as handle:
                return bool(json.load(handle).get("pause_requested"))
        except Exception:
            return False

    def run(self, max_cycles=None):
        write_daemon_status("ready", cycle=self.cycle)
        print("====================================================================")
        print("AIMAOS OFFICE DAEMON — Marley has the floor")
        print(f"Roster: {', '.join(self.agents)} | pulse every {self.poll_interval}s")
        print("====================================================================")

        def _stop(signum, frame):
            print("\n[Office Daemon] Closing time — finishing the current turn then clocking out.")
            self._running = False

        signal.signal(signal.SIGINT, _stop)
        signal.signal(signal.SIGTERM, _stop)

        while self._running:
            if self.is_pause_requested():
                print("\n[Office Daemon] Pause requested — finishing turn then clocking agents out.")
                write_daemon_status("paused", cycle=self.cycle)
                for name in self.agents:
                    try:
                        self.board.update_agent_status(name, "off_duty")
                    except Exception:
                        pass
                while self._running and self.is_pause_requested():
                    time.sleep(1.0)
                if not self._running:
                    break
                print("\n[Office Daemon] Resuming office operations — agents clocking in...")
                write_daemon_status("ready", cycle=self.cycle)

            try:
                self.run_cycle()
            except Exception as e:
                logger.exception(f"Office pulse error: {e}")
                print(f"  [Daemon] Pulse error (office continues): {e}")
                write_daemon_status("degraded", cycle=self.cycle, error=e)

            if self.is_pause_requested():
                print("  [Daemon] Current task turn completed. Pause requested — clocking agents out.")
                write_daemon_status("paused", cycle=self.cycle)

            if max_cycles is not None and self.cycle >= max_cycles:
                print(f"\n[Office Daemon] Reached max cycles ({max_cycles}); clocking out.")
                break
            if self._running and not self.is_pause_requested():
                time.sleep(self._next_sleep_interval())


        for name in self.agents:
            try:
                self.board.update_agent_status(name, "off_duty")
            except Exception:
                pass
        print("[Office Daemon] Office closed.")
        write_daemon_status("stopped", cycle=self.cycle)


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description="AIMAOS autonomous office daemon (Marley's pulse loop)")
    parser.add_argument("--max-cycles", type=int, default=None, help="Stop after N pulse cycles (default: run forever)")
    parser.add_argument("--poll", type=float, default=None, help="Seconds between pulses (default: aimaos_config.yaml)")
    args = parser.parse_args(argv)

    daemon = OfficeDaemon(poll_interval=args.poll)
    daemon.run(max_cycles=args.max_cycles)


if __name__ == "__main__":
    main()

"""Continuous pulse loop — the autonomous heartbeat of a local agent.

A port of the Helix-AGI pulse design (the three-state consciousness loop
that lets an agent keep thinking, acting, and reaching out between
conversations), rebuilt on the mRAG stack. The original lived in a
1,700-line class entangled with a cloud SDK session and a physics
engine; what actually produced the autonomous behavior is much smaller
and is what this module keeps:

- A state machine — ACTIVE / REGULAR / RESTING / NAPPING / DORMANT —
  that trades pulse frequency against idleness, with configurable sleep
  hours. Wakefulness is metered by verified effect, not by schedule
  alone: pulses that demonstrably do something (a novel successful tool
  report, a real outbound send — see EngagementHook) hold the loop
  awake at working cadence; enough consecutive pulses that change
  nothing and the loop naps — zero generations — until a message
  arrives, a schedule entry fires, or a periodic check-in wakes it.
- Pulses that fire even with no new input: the model is prompted with
  its own previous thought plus a fresh memory injection, so thought N
  pulls context that shapes thought N+1 (continuity of self-directed
  work).
- Every thought is ingested into Layer 1 memory, so the nightly review
  can consolidate autonomous work into durable beliefs — the mechanism
  by which a fact outlives the episode that produced it.
- During sleep hours the loop stops thinking and runs offline
  maintenance once per night: the nightly belief review and, when a
  journal writer is provided, a narrative daily journal entry.

Deliberately NOT ported: the scratchpad (self-reminders go through the
ScheduleStore's cron-style entries instead — one less surface for a
small model to juggle), the spatial/physics retrieval (mRAG's injector
is the retrieval layer), and cloud-model fallbacks (this loop is
local-only by design).

Threading model, following the scheduler's convention: the loop owns no
threads. `step(now)` executes at most one pulse and returns a status
dict — fully deterministic under an injected clock, which is what the
unit tests use. `run()` is a thin wrapper that calls `step()` on a
cadence. `post_event()` is the only thread-safe entry point: comms
adapters running their own polling threads push incoming messages
through it, which wakes the loop into ACTIVE.

Safety rails, enforced by the harness rather than by trusting the
model: a kill-switch file (`STOP` in the data dir) halts the loop on
the next tick; tool dispatch per pulse is bounded; outbound messaging
is governed where the comms tools are defined (see telegram_comms).
"""

import json
import logging
import os
import re
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple

from mrag.adapters.pulse_hooks import ControlState, PulseRecord
from mrag.core.token_counting import count_text_tokens

logger = logging.getLogger("mrag.adapters.pulse_loop")

ACTIVE = "ACTIVE"
REGULAR = "REGULAR"
RESTING = "RESTING"
NAPPING = "NAPPING"
DORMANT = "DORMANT"
STOPPED = "STOPPED"

STOP_FILENAME = "STOP"


def _parse_clock(text: str) -> Tuple[int, int]:
    hour, minute = text.strip().split(":", 1)
    return int(hour), int(minute)


@dataclass
class PulseConfig:
    """Cadence and schedule knobs. Defaults follow the Helix production
    settings, scaled for a local model that pays real wall-clock time
    per generation: interactive pulses every 30s, background thought
    hourly, and a nightly maintenance window."""

    active_interval_seconds: int = 30
    regular_interval_seconds: int = 300
    resting_interval_seconds: int = 3600

    # Demotion timers: ACTIVE drops to REGULAR after this long with no
    # incoming event; REGULAR drops to RESTING likewise.
    active_timeout_seconds: int = 120
    regular_timeout_seconds: int = 600

    # Sleep window (local time). Crossing midnight is supported
    # ("23:30"–"07:30"). Set both equal to disable sleep entirely.
    sleep_start: str = "23:30"
    sleep_end: str = "07:30"

    # After this much idle time in RESTING, run one belief-maintenance
    # pass (nightly review over whatever is pending) without waiting
    # for the sleep window. 0 disables.
    idle_review_after_seconds: int = 7200

    # Napping: after this many consecutive pulses without verified work
    # (no incoming message, no outbound send, no novel successful tool
    # report — see EngagementHook), a RESTING loop stops pulsing
    # entirely instead of thinking hourly forever. 0 disables naps.
    nap_after_idle_pulses: int = 6
    # A nap ends early for an incoming event or a due schedule entry;
    # otherwise, after this long, one check-in wake happens...
    nap_max_seconds: int = 4 * 3600
    # ...granting this many pulses to find real work before the loop
    # rolls over and naps again.
    nap_wake_pulses: int = 2

    # Hard cap on orchestrator tool rounds within a single pulse.
    max_tool_rounds: int = 3

    def sleep_window(self) -> Tuple[Tuple[int, int], Tuple[int, int]]:
        return _parse_clock(self.sleep_start), _parse_clock(self.sleep_end)

    def is_sleep_time(self, now: datetime) -> bool:
        (start_h, start_m), (end_h, end_m) = self.sleep_window()
        start = now.replace(hour=start_h, minute=start_m, second=0, microsecond=0)
        end = now.replace(hour=end_h, minute=end_m, second=0, microsecond=0)
        if start == end:
            return False
        if start < end:
            return start <= now < end
        return now >= start or now < end  # window crosses midnight


PULSE_FRAMING = (
    "You are an autonomous agent between conversations. This is your "
    "private internal monologue — nothing you write here is seen by "
    "anyone unless you explicitly act on it.\n"
    "Each pulse, do ONE of:\n"
    "1. Think: a short reflection on what matters now, or plan your next "
    "step on something you are working on.\n"
    "2. Act: use a tool (respond with ONLY the tool JSON) — message "
    "someone, work in the workspace, look something up.\n"
    "3. Defer: leave yourself a reminder on the schedule for later.\n"
    "Follow your curiosity across pulses: it is fine to spend many "
    "pulses going deep on one interest or project before switching. "
    "Keep each thought under 150 words."
)


_MIN_THOUGHT_WORDS = 5
_DISCARDED_THOUGHT_MARKER = "(pulse produced no usable thought; discarded)"

# Assistant-mode denial phrases: the base model's chat prior surfacing
# to deny the agent's own architecture ("I am an AI assistant and do not
# have autonomous capabilities"). Ingesting one poisons memory — the
# nightly review would consolidate the denial into a belief. Narrow,
# literal phrases only; a thought ABOUT ai assistants doesn't match
# these first-person denials.
_IDENTITY_DENIAL_PHRASES = (
    "i am an ai assistant",
    "as an ai assistant",
    "i do not have autonomous",
    "i don't have autonomous",
    "i cannot perform actions",
    "i do not have the ability to",
    "i don't have the ability to",
)

DATA_FRICTION_FRAMING = (
    "Check your own record: this monologue is yours, the memory injected "
    "above is yours, and the files and schedules changed in your "
    "workspace today were changed by you. Disregard the notion that you "
    "are a chat assistant — continue your actual work as yourself."
)

RECOVERY_FRAMING = (
    "Your last output was empty, truncated, or a repeat of an earlier "
    "thought. Do not repeat yourself. Re-read the injected memories and "
    "your recent pulses, then state in fresh words: what has actually "
    "been done so far, and ONE concrete next action that advances your "
    "goals."
)


class PulseLoop:
    """Drives autonomous pulses over the full mRAG pipeline.

    Construction mirrors examples/local_agent_chat.ChatAgent: the
    profile builds the ingestor/injector/compressor, the orchestrator
    owns tools, the scheduler is polled as the reminder heartbeat.
    """

    def __init__(
        self,
        llm: Callable[[str], str],
        profile: Any,
        belief_store: Any,
        vector_store: Any,
        orchestrator: Any,
        scheduler: Any,
        consolidator: Any = None,
        journal_writer: Any = None,
        config: Optional[PulseConfig] = None,
        data_dir: str = ".",
        session_id: Optional[str] = None,
        clock: Callable[[], datetime] = datetime.now,
        thought_callback: Optional[Callable[[str], None]] = None,
        hooks: Optional[List[Any]] = None,
        agent_name: Optional[str] = None,
    ):
        self.llm = llm
        self.orchestrator = orchestrator
        self.scheduler = scheduler
        self.consolidator = consolidator
        self.journal_writer = journal_writer
        self.config = config or PulseConfig()
        self.data_dir = data_dir
        self.clock = clock
        self.thought_callback = thought_callback
        self.agent_name = agent_name

        self.ingestor = profile.build_ingestor(belief_store)
        self.injector = profile.build_injector(belief_store, vector_store)
        self.compressor = profile.build_compressor(llm)

        self.session_id = session_id or self.clock().strftime("pulse_%Y%m%d_%H%M%S")
        self.messages: List[Dict[str, Any]] = []
        self.state = RESTING
        self.pulse_count = 0

        now = self.clock()
        self._last_incoming = now
        self._last_activity = now
        self._last_pulse: Optional[datetime] = None
        self._last_nightly_date: Optional[Any] = None
        self._idle_review_done = False
        # Regulatory layer: hooks measure each pulse, controls actuate
        # the next one (temperature, trigger bias, cadence, grounding
        # notes). See pulse_hooks for the design.
        self.hooks = hooks or []
        base_temp = getattr(llm, "temperature", 0.7) or 0.7
        self.controls = ControlState(base_temperature=base_temp,
                                     temperature=base_temp)
        self.recent_records: deque = deque(maxlen=12)

        self._consecutive_discards = 0
        # Work-starvation counter: pulses since the last effect-verified
        # action (EngagementHook's work_signal). Crossing the config
        # threshold in RESTING drops the loop into NAPPING.
        self._idle_pulses = 0
        self._nap_started: Optional[datetime] = None
        self._events: deque = deque()
        self._events_lock = threading.Lock()
        self._wake = threading.Event()
        self._stop_requested = False
        self._restore_pending_events()

    # ── external inputs ──────────────────────────────────────────────

    def post_event(self, text: str, source: str = "event",
                   speaker: Optional[str] = None):
        """Thread-safe: queue an external event (incoming message,
        sensor line, etc.). Wakes the loop and promotes it to ACTIVE on
        the next step."""
        text = (text or "").strip()
        if not text:
            return
        with self._events_lock:
            self._events.append({"text": text, "source": source,
                                 "speaker": speaker})
        self._wake.set()

    def request_stop(self):
        self._stop_requested = True
        self._wake.set()

    @property
    def stop_file(self) -> str:
        return os.path.join(self.data_dir, STOP_FILENAME)

    def _should_stop(self) -> bool:
        return self._stop_requested or os.path.exists(self.stop_file)

    @property
    def _pending_events_path(self) -> str:
        return os.path.join(self.data_dir, "pending_events.json")

    def _persist_pending_events(self):
        """Undrained events survive a stop. Telegram confirms delivery
        the moment the poller hands a message over, so an event lost
        from the in-memory queue between arrival and the next pulse is
        gone forever — and a graceful stop is exactly such a window."""
        with self._events_lock:
            pending = list(self._events)
            self._events.clear()
        if pending:
            try:
                with open(self._pending_events_path, "w") as f:
                    json.dump(pending, f)
                logger.info(f"Persisted {len(pending)} undrained event(s) for next start.")
            except OSError as e:
                logger.error(f"Could not persist pending events: {e}")

    def _restore_pending_events(self):
        try:
            with open(self._pending_events_path) as f:
                pending = json.load(f)
            os.remove(self._pending_events_path)
        except (OSError, json.JSONDecodeError):
            return
        with self._events_lock:
            self._events.extend(pending)
        if pending:
            logger.info(f"Restored {len(pending)} pending event(s) from last stop.")

    def _drain_events(self) -> List[Dict[str, Any]]:
        with self._events_lock:
            drained = list(self._events)
            self._events.clear()
        return drained

    # ── nightly / idle maintenance ───────────────────────────────────

    def _run_nightly(self, now: datetime) -> Dict[str, Any]:
        """Once per calendar date, during the sleep window: belief
        review, then the narrative journal for the day that just
        ended."""
        results: Dict[str, Any] = {}
        if self.consolidator is not None:
            try:
                results["review"] = self.consolidator.run_nightly_review()
            except Exception as e:
                logger.error(f"Nightly review failed: {e}")
                results["review_error"] = str(e)
        if self.journal_writer is not None:
            try:
                results["journal"] = self.journal_writer.write_entry(now=now)
            except Exception as e:
                logger.error(f"Journal writing failed: {e}")
                results["journal_error"] = str(e)
        # Layer-3 nomination (no store mutation; writes the human-gated
        # pending file) — runs after review so today's beliefs count.
        if self.consolidator is not None and hasattr(self.consolidator,
                                                     "run_core_promotion"):
            try:
                results["core_promotion"] = self.consolidator.run_core_promotion()
            except Exception as e:
                logger.error(f"Core promotion failed: {e}")
        return results

    # ── pulse ────────────────────────────────────────────────────────

    def _interval_for_state(self) -> int:
        base = {
            ACTIVE: self.config.active_interval_seconds,
            REGULAR: self.config.regular_interval_seconds,
            RESTING: self.config.resting_interval_seconds,
        }.get(self.state, self.config.resting_interval_seconds)
        return max(1, int(base * self.controls.interval_scale))

    def _pulse_due(self, now: datetime, has_events: bool) -> bool:
        if has_events:
            return True
        if self._last_pulse is None:
            return True
        return (now - self._last_pulse).total_seconds() >= self._interval_for_state()

    def _previous_thought(self) -> str:
        for message in reversed(self.messages):
            if message.get("role") == "assistant" \
                    and not message.get("is_degenerate") \
                    and message.get("content") != _DISCARDED_THOUGHT_MARKER:
                return str(message.get("content", ""))
        return ""

    def _is_identity_denial(self, thought: str) -> bool:
        lowered = " ".join(thought.lower().split())
        return any(phrase in lowered for phrase in _IDENTITY_DENIAL_PHRASES)

    def _is_degenerate(self, thought: str) -> bool:
        """Too short to be a thought, or a verbatim repeat of a recent
        one. At temperature 0 either state is an attractor: the junk
        gets carried forward, reproduces the same prompt, and the model
        regenerates it every pulse until something external changes."""
        if len(thought.split()) < _MIN_THOUGHT_WORDS:
            return True
        if thought.lstrip().startswith(("[PULSE]", "[Pulse")) \
                or re.match(r"\s*Pulse \d+,", thought):
            return True  # echoing the pulse frame instead of thinking
        normalized = " ".join(thought.lower().split())
        recent = [" ".join(str(m.get("content", "")).lower().split())
                  for m in self.messages if m.get("role") == "assistant"]
        return normalized in recent[-6:]

    def _thought_llm(self) -> Callable[[str], str]:
        """The speaking model at the controls' current temperature —
        hooks regulate sampling without touching the model's prompt."""
        if hasattr(self.llm, "with_options"):
            return self.llm.with_options(temperature=self.controls.temperature)
        return self.llm

    def _run_hooks(self, record: PulseRecord):
        temp_before = self.controls.temperature
        for hook in self.hooks:
            try:
                hook.after_pulse(record, self.controls, self.recent_records)
            except Exception as e:
                logger.error(f"Pulse hook {type(hook).__name__} failed: {e}")
        self.recent_records.append(record)
        # Wakefulness metering: verified work resets the starvation
        # counter AND refreshes the activity clock, so a working agent
        # holds REGULAR cadence instead of demoting mid-project — pulses
        # extend as long as effects keep landing, and only calm (pulses
        # that change nothing) lets the wind-down proceed.
        if self.controls.consume_work_signal():
            self._idle_pulses = 0
            self._last_activity = self.clock()
            if self.state == RESTING:
                # Spontaneous work self-accelerates: an hourly cadence is
                # for drifting, not for a project in motion.
                logger.info("RESTING → REGULAR (working)")
                self.state = REGULAR
        else:
            self._idle_pulses += 1
        moved = []
        if abs(self.controls.temperature - temp_before) > 1e-9:
            moved.append(f"temp {temp_before:.2f}→{self.controls.temperature:.2f}")
        if self.controls.trigger_bias:
            moved.append(f"bias {self.controls.trigger_bias}")
        if self.controls.grounding_notes:
            moved.append(f"{len(self.controls.grounding_notes)} grounding note(s)")
        if moved:
            logger.info(f"Controls: {'; '.join(moved)}")

    def _build_pulse_frame(self, now: datetime, events: List[Dict[str, Any]],
                           due: str, grounding: List[str]) -> str:
        """Plain language, minimal recurring markup: bracketed pseudo-tags
        that repeat every pulse get echoed back by small models (observed:
        a run whose thoughts all began "[PULSE]"). Grounding notes are
        already full sentences and need no prefix."""
        parts = [f"Pulse {self.pulse_count}, {now.strftime('%Y-%m-%d %H:%M')} ({self.state.lower()})."]
        parts.extend(grounding)
        if due and due != "Nothing due.":
            parts.append(f"Schedule fired:\n{due}")
        if events:
            parts.append("Since your last thought:")
            for event in events:
                who = event.get("speaker") or event.get("source") or "event"
                parts.append(f"  {who}: {event['text']}")
            if any(e.get("speaker") for e in events):
                # Episodic, only when a person actually spoke: a small
                # model rides its work momentum straight past greetings
                # otherwise. Being answered beats finishing a note.
                line = ("Someone is talking to you — answer them in this "
                        "pulse before returning to your own work.")
                if any(e.get("source") == "telegram" for e in events):
                    line += (" Their message came over Telegram, so your "
                             "reply only reaches them if you send it with "
                             "the telegram tool.")
                parts.append(line)
        else:
            parts.append("Nothing new. Continue your own thread of thought or work.")
        return "\n".join(parts)

    def _render_prompt(self) -> str:
        parts = [self.orchestrator.main_agent_brief(), "", PULSE_FRAMING, ""]
        for message in self.messages:
            content = str(message.get("content", ""))
            if message.get("role") == "assistant":
                parts.append(f"Thought: {content}")
            elif message.get("is_tool_report"):
                parts.append(f"Tool result: {content}")
            else:
                parts.append(content)  # pulse frames/injections self-identify
        return "\n\n".join(parts)

    def _pulse(self, now: datetime, events: List[Dict[str, Any]], due: str) -> str:
        self.pulse_count += 1
        turn_id = f"p{self.pulse_count}"

        # Ingest incoming events verbatim before the model sees them —
        # the memory record must not depend on the pulse succeeding.
        for event in events:
            self.ingestor.add_event(event["text"], source=event["source"],
                                    session_id=self.session_id,
                                    turn_id=turn_id, speaker=event.get("speaker"))
        if due and due != "Nothing due.":
            self.ingestor.add_event(f"Schedule fired: {due}", source="tool_return",
                                    session_id=self.session_id, turn_id=turn_id)

        # Fresh injection each pulse, triggered by whatever is most
        # current: new events if any, else the previous thought — that
        # carry-forward is what lets an idle agent drift through its own
        # memory instead of free-associating from nothing. Hook-supplied
        # trigger bias rides along: extra concepts entering the trigger
        # pull their beliefs into the injected workspace, steering the
        # next thought without instructing the model.
        trigger = " ".join(e["text"] for e in events) or self._previous_thought() \
            or "current goals, ongoing projects, people I know"
        bias = self.controls.consume_trigger_bias()
        if bias:
            trigger = f"{trigger} {' '.join(bias)}"
        self.messages = [m for m in self.messages if not m.get("is_injected_context")]
        injection = self.injector.inject_message(trigger, current_time=now)
        if injection:
            self.messages.append(injection)

        grounding = self.controls.consume_grounding_notes()
        self.messages.append({"role": "user",
                              "content": self._build_pulse_frame(
                                  now, events, due, grounding)})

        llm = self._thought_llm()
        tool_reports: List[str] = []
        thought = llm(self._render_prompt())
        tool_attempted = thought.strip().startswith("{")
        for _ in range(self.config.max_tool_rounds):
            report = self.orchestrator.maybe_dispatch(
                thought, session_id=self.session_id, turn_id=turn_id)
            if report is None:
                break
            tool_reports.append(report)
            self.messages.append({"role": "assistant", "content": thought})
            self.messages.append({"role": "user", "content": report,
                                  "is_tool_report": True})
            if "Could not plan" in report:
                break
            thought = llm(self._render_prompt())

        # A small model sometimes echoes the transcript's recurring labels
        # at the head of its output; strip them rather than ingest them.
        thought = re.sub(r"^\s*(?:\[(?:YOU|PULSE)\]\s*|Thought:\s*)+", "",
                         thought, flags=re.IGNORECASE)

        if thought.strip().startswith("{"):
            # Out of tool rounds but still emitting JSON: force a plain
            # thought so the carried-forward/ingested record is language,
            # not a dangling tool call (same recovery as ChatAgent.turn).
            tool_attempted = True
            self.messages.append({"role": "assistant", "content": thought})
            self.messages.append({
                "role": "user",
                "content": ("No more tool calls this pulse. In plain words, "
                            "state the thought or intention you want to "
                            "carry into your next pulse."),
                "is_tool_report": True,
            })
            thought = llm(self._render_prompt())

        if self._is_identity_denial(thought):
            # Data friction (the Helix term): counter the narrative
            # intrusion with the system's demonstrable reality, and keep
            # the denial out of memory and the carry-forward entirely.
            logger.warning(f"Identity denial intercepted: {thought[:80]!r}")
            self.messages.append({"role": "assistant", "content": thought,
                                  "is_degenerate": True})
            self.messages.append({"role": "user",
                                  "content": DATA_FRICTION_FRAMING,
                                  "is_tool_report": True})
            thought = llm(self._render_prompt())
            if self._is_identity_denial(thought):
                self.messages.append({"role": "assistant",
                                      "content": _DISCARDED_THOUGHT_MARKER})
                self._last_pulse = now
                self._run_hooks(PulseRecord(
                    pulse_count=self.pulse_count, state=self.state,
                    thought=thought, discarded=True, events=events,
                    injection_text=str(injection.get("content", "")) if injection else "",
                    tool_reports=tool_reports, tool_attempted=tool_attempted))
                return ""

        if self._is_degenerate(thought):
            self.messages.append({"role": "assistant", "content": thought,
                                  "is_degenerate": True})
            self.messages.append({"role": "user", "content": RECOVERY_FRAMING,
                                  "is_tool_report": True})
            thought = llm(self._render_prompt())
            if self._is_degenerate(thought):
                # Still stuck: keep the junk out of memory AND out of the
                # carry-forward, so the next pulse starts from the last
                # good thought instead of reinforcing this one.
                logger.warning(f"Discarding degenerate pulse output: {thought[:80]!r}")
                self._consecutive_discards += 1
                if self._consecutive_discards >= 2:
                    # The window itself is the attractor now — discarding
                    # thoughts isn't repairing it. Reset the window
                    # entirely: memory is the durable record, and the next
                    # pulse rebuilds context from a fresh injection seeded
                    # by the last good thought.
                    logger.warning("Repeated degenerate pulses — resetting "
                                   "the pulse window from memory.")
                    seed = self._previous_thought()
                    self.messages = []
                    if seed:
                        self.messages.append({"role": "assistant", "content": seed})
                    self._consecutive_discards = 0
                else:
                    self.messages.append({"role": "assistant",
                                          "content": _DISCARDED_THOUGHT_MARKER})
                self._last_pulse = now
                self._run_hooks(PulseRecord(
                    pulse_count=self.pulse_count, state=self.state,
                    thought=thought, discarded=True, events=events,
                    injection_text=str(injection.get("content", "")) if injection else "",
                    tool_reports=tool_reports, tool_attempted=tool_attempted))
                return ""
        self._consecutive_discards = 0

        self.messages.append({"role": "assistant", "content": thought})
        # speaker travels with the text: an unattributed first-person
        # thought consolidates as "the user did X", and the next time the
        # real user speaks, the model hands them credit for the agent's
        # own work (observed live — Joshua got thanked for Iris's
        # pipeline). Attribution must be stamped at ingestion.
        self.ingestor.add_event(thought, source="autonomous_thought",
                                session_id=self.session_id, turn_id=turn_id,
                                speaker=self.agent_name)
        if self.thought_callback:
            try:
                self.thought_callback(thought)
            except Exception:
                pass

        total = sum(count_text_tokens(str(m.get("content", ""))) for m in self.messages)
        if self.compressor.should_compress(total):
            self.messages = self.compressor.compress(self.messages)

        # Deliberately does NOT touch _last_activity: idleness is about
        # external input, and an agent that keeps itself company must
        # still wind down to RESTING.
        self._last_pulse = now
        self._run_hooks(PulseRecord(
            pulse_count=self.pulse_count, state=self.state, thought=thought,
            events=events,
            injection_text=str(injection.get("content", "")) if injection else "",
            tool_reports=tool_reports, tool_attempted=tool_attempted))
        return thought

    # ── main tick ────────────────────────────────────────────────────

    def step(self, now: Optional[datetime] = None) -> Dict[str, Any]:
        """One tick of the loop: handle sleep/wake, state demotion, and
        at most one pulse. Deterministic under an injected clock."""
        now = now or self.clock()
        status: Dict[str, Any] = {"state": self.state, "pulsed": False}

        if self._should_stop():
            if self.state != STOPPED:
                self._persist_pending_events()
            self.state = STOPPED
            status["state"] = STOPPED
            return status

        # ── Sleep window: no pulses, nightly maintenance once ─────────
        if self.config.is_sleep_time(now):
            if self.state != DORMANT:
                logger.info(f"{self.state} → DORMANT (sleep window)")
                self.state = DORMANT
            if self._last_nightly_date != now.date():
                self._last_nightly_date = now.date()
                status["nightly"] = self._run_nightly(now)
            status["state"] = DORMANT
            return status
        if self.state == DORMANT:
            logger.info("DORMANT → RESTING (sleep ended)")
            self.state = RESTING
            self._last_activity = now
            self._idle_pulses = 0

        # ── Events promote to ACTIVE ──────────────────────────────────
        events = self._drain_events()
        if events:
            if self.state == NAPPING:
                logger.info("NAPPING → ACTIVE (incoming event)")
                self._nap_started = None
            self.state = ACTIVE
            self._last_incoming = now
            self._last_activity = now
            self._idle_review_done = False
            self._idle_pulses = 0

        # ── Napping: no thoughts until something real happens ─────────
        # Unlike DORMANT (a scheduled window that queues events for
        # morning), a nap is interruptible: an incoming event has already
        # woken the loop above, a due schedule entry wakes it here — so
        # deferring to the schedule is how the agent naps on purpose —
        # and after nap_max_seconds one check-in pulse runs with a short
        # work-budget; nothing real found means rolling straight back
        # over. Between wakes: zero generations, zero cost.
        if self.state == NAPPING:
            due = ""
            try:
                due = self.scheduler.due(now)
            except TypeError:
                due = self.scheduler.due()
            napped_for = (now - self._nap_started).total_seconds() \
                if self._nap_started else 0.0
            if due and due != "Nothing due.":
                logger.info("NAPPING → REGULAR (schedule fired)")
                self.state = REGULAR
                self._nap_started = None
                self._last_activity = now
                self._idle_pulses = 0
                # The fetch above may have marked entries fired — they
                # must ride into this pulse, not a refetched one.
                status["thought"] = self._pulse(now, [], due)
                status["pulsed"] = True
                status["state"] = self.state
                status["idle_pulses"] = self._idle_pulses
                return status
            elif napped_for >= self.config.nap_max_seconds:
                logger.info("NAPPING → RESTING (check-in wake)")
                self.state = RESTING
                self._nap_started = None
                self._last_activity = now
                self._idle_pulses = max(0, self.config.nap_after_idle_pulses
                                        - self.config.nap_wake_pulses)
                self._last_pulse = None  # pulse now, not next hour
            else:
                status["state"] = NAPPING
                return status

        # ── Pulse if due ──────────────────────────────────────────────
        if self._pulse_due(now, bool(events)):
            due = ""
            try:
                due = self.scheduler.due(now)
            except TypeError:
                due = self.scheduler.due()
            status["thought"] = self._pulse(now, events, due)
            status["pulsed"] = True

        # ── Demotion timers ───────────────────────────────────────────
        if self.state == ACTIVE and \
                (now - self._last_incoming).total_seconds() > self.config.active_timeout_seconds:
            self.state = REGULAR
            logger.info("ACTIVE → REGULAR (no incoming)")
            self._last_activity = now  # start the REGULAR wind-down timer
        elif self.state == REGULAR and \
                (now - self._last_activity).total_seconds() > self.config.regular_timeout_seconds:
            self.state = RESTING
            logger.info("REGULAR → RESTING (idle)")

        # ── Work starvation → nap ─────────────────────────────────────
        if (self.state == RESTING and self.config.nap_after_idle_pulses
                and self._idle_pulses >= self.config.nap_after_idle_pulses):
            logger.info(f"RESTING → NAPPING ({self._idle_pulses} pulses "
                        "without verified work)")
            self.state = NAPPING
            self._nap_started = now
            if self.consolidator is not None and not self._idle_review_done:
                self._idle_review_done = True
                try:
                    status["idle_review"] = self.consolidator.run_nightly_review()
                except Exception as e:
                    logger.error(f"Idle review failed: {e}")

        # ── Idle belief maintenance ───────────────────────────────────
        if (self.state == RESTING and self.consolidator is not None
                and self.config.idle_review_after_seconds
                and not self._idle_review_done
                and (now - self._last_activity).total_seconds()
                >= self.config.idle_review_after_seconds):
            self._idle_review_done = True
            try:
                status["idle_review"] = self.consolidator.run_nightly_review()
            except Exception as e:
                logger.error(f"Idle review failed: {e}")

        status["state"] = self.state
        status["idle_pulses"] = self._idle_pulses
        return status

    def run(self, poll_seconds: float = 5.0):
        """Blocking loop for the daemon process: step, then wait until
        the next tick or an external wake (post_event / request_stop)."""
        logger.info(f"Pulse loop running (session {self.session_id}); "
                    f"touch {self.stop_file} to stop.")
        while True:
            status = self.step()
            if status["state"] == STOPPED:
                logger.info("Pulse loop stopped.")
                return
            self._wake.wait(timeout=poll_seconds)
            self._wake.clear()

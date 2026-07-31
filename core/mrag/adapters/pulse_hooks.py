"""Post-pulse hooks — the regulatory nervous system around the pulse loop.

Design principle (from Helix-AGI's post-pulse hook layer, and consonant
with Anthropic's J-space finding that a small privileged set of
verbalizable concepts acts as a model's global workspace, where swapping
a concept changes downstream behavior): don't push self-regulation onto
the speaking model as instructions. The model is the language center;
regulation lives in the harness. Hooks MEASURE each pulse and adjust
CONTROLS; the controls change what enters the model's workspace next —
which concepts get injected, how warm sampling runs, how fast pulses
fire, and what the system factually observed about the agent's own
actions. The model then reasons differently because its inputs changed,
not because it was told to.

The loop of directionality:

    thought → hooks measure → controls shift → next injection/frame
    differs → next thought differs → ...

Actuators (ControlState):
- temperature      arousal: higher breaks repetition, lower restores focus
- trigger_bias     concepts appended to the next injection trigger — the
                   direct workspace-composition lever (consumed each pulse)
- interval_scale   metabolic rate: stretch or shrink the pulse cadence
- grounding_notes  factual observations injected into the next frame,
                   e.g. "[system] the last tool request failed to parse;
                   nothing was written" — senses, not exhortations
                   (consumed each pulse)

Sensors (hooks shipped here):
- StabilityHook    thought-over-thought similarity → temperature nudges
                   (the Helix stability→temperature mechanism, rebuilt)
- ToolReflexHook   tool dispatch outcomes → grounding notes, so failed or
                   unroutable tool calls are FELT next pulse instead of
                   silently vanishing behind a confabulated success claim
- ConceptFlowHook  concept dwell/scatter over the store's Layer-2 term
                   lexicon → trigger bias: long dwell on one cluster
                   raises curiosity pressure (bias toward least-recently
                   visited terms); rapid scatter raises focus pressure
                   (bias back toward the dominant recent thread)
- EngagementHook   effect-verified work detection (novel successful tool
                   reports, real outbound sends) → work_signal, which
                   the loop consumes to meter wakefulness: working
                   agents keep pulsing, idle or ruminating ones nap

Hooks are synchronous, CPU-only, and isolated: a hook exception is
logged and skipped, never fatal to the pulse.
"""

import logging
import re
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, List, Optional

logger = logging.getLogger("mrag.adapters.pulse_hooks")

_WORD = re.compile(r"[a-z0-9][a-z0-9'-]+")

# Common words excluded from similarity/concept measurement so metrics
# track substance, not connective tissue.
_STOPWORDS = frozenset("""
a an and are as at be been but by can could did do does for from had has
have how i if in into is it its just like me my next now of on or our
should so some than that the their them then these they this to was we
were what when which will with would you your
""".split())


def content_words(text: str) -> List[str]:
    return [w for w in _WORD.findall(text.lower()) if w not in _STOPWORDS]


def jaccard(a: List[str], b: List[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


@dataclass
class PulseRecord:
    """Everything observable about one completed pulse."""
    pulse_count: int
    state: str
    thought: str
    discarded: bool = False
    events: List[Dict[str, Any]] = field(default_factory=list)
    injection_text: str = ""
    tool_reports: List[str] = field(default_factory=list)
    tool_attempted: bool = False


@dataclass
class ControlState:
    """The actuator surface the hooks write and the pulse loop reads."""
    base_temperature: float = 0.7
    temperature: float = 0.7
    min_temperature: float = 0.2
    max_temperature: float = 1.1
    interval_scale: float = 1.0
    trigger_bias: List[str] = field(default_factory=list)
    grounding_notes: List[str] = field(default_factory=list)
    # Set by EngagementHook when a pulse demonstrably did something new
    # in the world; the loop consumes it to meter wakefulness.
    work_signal: bool = False

    def nudge_temperature(self, delta: float):
        self.temperature = max(self.min_temperature,
                               min(self.max_temperature, self.temperature + delta))

    def relax_temperature(self, rate: float = 0.5):
        """Decay back toward base — regulation is pressure, not a latch."""
        self.temperature += (self.base_temperature - self.temperature) * rate

    def consume_trigger_bias(self) -> List[str]:
        bias, self.trigger_bias = self.trigger_bias, []
        return bias

    def consume_grounding_notes(self) -> List[str]:
        notes, self.grounding_notes = self.grounding_notes, []
        return notes

    def consume_work_signal(self) -> bool:
        signal, self.work_signal = self.work_signal, False
        return signal


class PulseHook:
    """Base class; subclasses override after_pulse."""

    def after_pulse(self, record: PulseRecord, controls: ControlState,
                    history: Deque[PulseRecord]):
        raise NotImplementedError


class StabilityHook(PulseHook):
    """Thought-over-thought similarity → temperature regulation.

    High overlap between consecutive thoughts means the workspace is
    congealing (the run-1 death spiral in slow motion): warm sampling to
    shake it loose. Low overlap means exploration is healthy: relax back
    toward base. A discarded pulse is maximal instability of the other
    kind (degenerate output), and also warms sampling — the degeneracy
    guard handles the window; this handles the sampler.
    """

    def __init__(self, high_similarity: float = 0.6, warm_step: float = 0.15):
        self.high_similarity = high_similarity
        self.warm_step = warm_step
        self.last_similarity: Optional[float] = None

    def after_pulse(self, record, controls, history):
        if record.discarded:
            controls.nudge_temperature(self.warm_step)
            return
        previous = next(
            (r for r in reversed(history) if not r.discarded and r.thought),
            None)
        if previous is None:
            return
        self.last_similarity = jaccard(content_words(record.thought),
                                       content_words(previous.thought))
        if self.last_similarity >= self.high_similarity:
            controls.nudge_temperature(self.warm_step)
        else:
            controls.relax_temperature()


class ToolReflexHook(PulseHook):
    """Tool outcomes become next-pulse senses.

    The confabulated-completion failure mode: a tool request fails to
    parse or errors, the report scrolls by, and the next thought claims
    success anyway. Instructing the model to be careful is pushing
    regulation onto the language center; instead, when a pulse's tool
    dispatch failed, the next frame carries a factual observation the
    model cannot miss. It also stretches nothing and blocks nothing —
    the agent stays free, it just can't NOT know what happened.
    """

    # Structured markers only. Bare words ("error", "failed") false-
    # positive on reports that merely QUOTE content mentioning past
    # failures — e.g. reading back a project log that documents a fixed
    # bug — and repeated false "did NOT complete" notes train learned
    # helplessness. "ERROR:"/"CONFIG ERROR:" are the starter-tool return
    # conventions; "could not plan" is the orchestrator's.
    FAILURE_MARKERS = ("could not plan", "error:", "config error")

    def after_pulse(self, record, controls, history):
        for report in record.tool_reports:
            lowered = report.lower()
            if any(marker in lowered for marker in self.FAILURE_MARKERS):
                controls.grounding_notes.append(
                    "Your last tool request did NOT complete — the report "
                    f"was: {report[:200]}. No work was saved by that call.")
                return
        if record.tool_attempted and not record.tool_reports:
            controls.grounding_notes.append(
                "Your last output looked like a tool call but could not be "
                "dispatched. No tool ran and no work was saved.")


class SendClaimHook(PulseHook):
    """Verifies claims of having messaged someone against the transport
    ground truth. The failure it exists for, observed live twice: a
    thought asserts "I have replied to Joshua via Telegram" with zero
    tool dispatch and zero transport activity — pure narrative
    completion that neither the failed-report nor the undispatched-JSON
    reflex can see, because nothing was attempted at all. The governor's
    monotonic send counter is authoritative: if the claim pattern
    matches and the counter didn't move this pulse, the next frame
    carries the correction."""

    CLAIM_PATTERN = re.compile(
        r"\b(replied|sent|messaged|responded)\b.{0,60}\b(telegram|message)\b"
        r"|\btelegram\b.{0,60}\b(sent|replied|delivered)\b",
        re.IGNORECASE | re.DOTALL)

    def __init__(self, governor: Any):
        self._governor = governor
        self._last_total = int(getattr(governor, "total_sends", 0))

    def after_pulse(self, record, controls, history):
        total = int(getattr(self._governor, "total_sends", 0))
        sent_this_pulse = total > self._last_total
        self._last_total = total
        if record.discarded or sent_this_pulse:
            return
        if self.CLAIM_PATTERN.search(record.thought):
            controls.grounding_notes.append(
                "No message left this machine during your last pulse — "
                "if that thought described sending one just now, it did "
                "not happen. To really reach someone, use the telegram "
                "tool and wait for its confirmation.")


class ConceptFlowHook(PulseHook):
    """Concept dwell and scatter over the store's Layer-2 lexicon →
    injection trigger bias. This is the workspace-composition lever: the
    next injection trigger carries extra terms, retrieval pulls their
    beliefs into the injected context, and the thought bends toward them
    — concepts move, not instructions.

    Dwell (same dominant concept for `dwell_limit` pulses) → curiosity:
    bias toward the least-recently-visited lexicon terms. Scatter (no
    concept repeated across recent pulses at all) → focus: bias back
    toward the most frequent recent concept.
    """

    def __init__(self, belief_store: Any, dwell_limit: int = 4,
                 bias_terms: int = 2, window: int = 5):
        self._store = belief_store
        self.dwell_limit = dwell_limit
        self.bias_terms = bias_terms
        self.window = window
        self._visits: Dict[str, int] = {}   # term -> last pulse seen
        self._dominant_streak = 0
        self._dominant_term: Optional[str] = None

    def _lexicon_terms(self) -> List[str]:
        try:
            beliefs = self._store.get_all_beliefs_flat()
        except Exception:
            return []
        terms = []
        for belief in beliefs:
            term = belief.get("term")
            if term and belief.get("_category") != "memory":
                terms.append(str(term).lower())
        return terms

    def after_pulse(self, record, controls, history):
        if record.discarded or not record.thought:
            return
        words = set(content_words(record.thought))
        terms = self._lexicon_terms()
        hit = [t for t in terms if t in words]
        for term in hit:
            self._visits[term] = record.pulse_count

        dominant = hit[0] if hit else None
        if dominant and dominant == self._dominant_term:
            self._dominant_streak += 1
        else:
            self._dominant_term = dominant
            self._dominant_streak = 1 if dominant else 0

        if self._dominant_streak >= self.dwell_limit:
            # Curiosity pressure: surface what the mind hasn't touched.
            unvisited = sorted(
                (t for t in terms if t != self._dominant_term),
                key=lambda t: self._visits.get(t, -1))
            fresh = unvisited[:self.bias_terms]
            if fresh:
                controls.trigger_bias.extend(fresh)
                self._dominant_streak = 0
            return

        recent = [r for r in list(history)[-self.window:] if not r.discarded]
        if len(recent) >= self.window and terms:
            recent_hits = [
                {t for t in terms if t in set(content_words(r.thought))}
                for r in recent
            ]
            overlap = set.intersection(*recent_hits) if recent_hits else set()
            if not overlap and not any(recent_hits[i] & recent_hits[i + 1]
                                       for i in range(len(recent_hits) - 1)):
                # Scatter: nothing carried between any adjacent pulses.
                counts: Dict[str, int] = {}
                for hits in recent_hits:
                    for term in hits:
                        counts[term] = counts.get(term, 0) + 1
                if counts:
                    focus = max(counts, key=counts.get)
                    controls.trigger_bias.append(focus)


class EngagementHook(PulseHook):
    """Detects whether a pulse did real work, by effect rather than by
    claim. Sets controls.work_signal, which the loop consumes to meter
    wakefulness: work extends pulsing, its absence lets the loop wind
    down into a nap instead of burning hourly pulses forever.

    A pulse counts as work only if it (a) actually sent an outbound
    message (the governor's monotonic counter moved), or (b) produced a
    successful tool report that is NOVEL against recent reports. The
    novelty test is the anti-rumination clause: re-reading or rewriting
    the same file yields near-duplicate reports, and an agent grinding
    in a circle should read as idle, not busy — that distinction is
    what separates "still working, stay up" from "calmed down, sleep".
    Pure thought never counts; thinking is what naps are recovering
    from, not what they wait for.
    """

    def __init__(self, governor: Any = None, novelty_threshold: float = 0.5,
                 report_memory: int = 10):
        self._governor = governor
        self._last_total = int(getattr(governor, "total_sends", 0) or 0)
        self.novelty_threshold = novelty_threshold
        self._recent_reports: Deque[List[str]] = deque(maxlen=report_memory)

    def after_pulse(self, record, controls, history):
        worked = False
        if self._governor is not None:
            total = int(getattr(self._governor, "total_sends", 0) or 0)
            worked = total > self._last_total
            self._last_total = total
        for report in record.tool_reports:
            lowered = report.lower()
            if any(m in lowered for m in ToolReflexHook.FAILURE_MARKERS):
                continue
            words = content_words(report)
            if all(jaccard(words, past) < self.novelty_threshold
                   for past in self._recent_reports):
                worked = True
            self._recent_reports.append(words)
        if worked:
            controls.work_signal = True


def default_hooks(belief_store: Any, governor: Any = None) -> List[PulseHook]:
    hooks: List[PulseHook] = [StabilityHook(), ToolReflexHook(),
                              ConceptFlowHook(belief_store),
                              EngagementHook(governor)]
    if governor is not None:
        hooks.append(SendClaimHook(governor))
    return hooks

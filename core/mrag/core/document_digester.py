"""Chunk-and-digest pipeline for oversized incoming events.

A local small-context agent can't afford to place a pasted document, long
tool return, or multi-page message directly into its working window — a
single such event could consume the whole thing. The DocumentDigester is
the escape hatch: the full text goes verbatim into Layer 1 memory (zero
loss, zero LLM calls, exact passages retrievable later), while the main
context receives only a compact digest.

The digest is produced map-reduce style with the *same* local model the
agent runs on, but each call is an independent prompt with its own fresh
context window — a throwaway subagent. Chunk size is chosen so one chunk
plus prompt scaffolding plus the summary output fits comfortably inside
the model's window; the main conversation context is never touched.

No timeouts are imposed anywhere on this path — a slow consumer-grade
box finishing in its own time beats a fast failure.
"""

import logging
from typing import Any, Callable, List, Optional

from mrag.core.memory_ingestor import MemoryIngestor, chunk_text, SOURCE_USER_INPUT
from mrag.core.token_counting import count_text_tokens

logger = logging.getLogger("mrag.core.document_digester")

_MAP_PROMPT = """Summarize this document section extractively in under {target_words} words.
- Keep every name, date, time, number, identifier, and direct quote exactly as written.
- Keep conclusions, decisions, and action items.
- Drop boilerplate, repetition, and filler.
Only output the summary, no preamble.

SECTION:
{section}"""

_REDUCE_PROMPT = """These are sequential section summaries of one document. Merge them into a single summary under {target_words} words.
- Preserve document order.
- Keep every name, date, time, number, identifier, and direct quote.
- Collapse redundancy across sections; do not add anything new.
Only output the merged summary, no preamble.

SECTION SUMMARIES:
{summaries}"""


class DocumentDigester:
    """Ingests an oversized text event into Layer 1 verbatim and returns a
    token-bounded digest for the main context window."""

    def __init__(
        self,
        llm_callable: Callable[[str], str],
        ingestor: Optional[MemoryIngestor] = None,
        map_chunk_tokens: int = 3000,
        digest_max_tokens: int = 800,
        large_event_threshold_tokens: int = 1500,
        max_reduce_rounds: int = 3,
    ):
        """
        Args:
            llm_callable: Prompt-in/string-out callable for the local model.
                Every call is independent — a fresh context window.
            ingestor: When given, the full raw text is stored to Layer 1
                memory before any summarization, so the digest is a
                convenience view and never the only copy.
            map_chunk_tokens: Per-map-call section size. Size it so section +
                prompt + output fit the local model's window (~25% of the
                window is a safe default).
            digest_max_tokens: Hard ceiling on the digest returned to the
                main context.
            large_event_threshold_tokens: should_digest() boundary — events
                at or under this pass through untouched.
            max_reduce_rounds: Bound on recursive reduce passes before
                falling back to extractive truncation.
        """
        self.llm = llm_callable
        self._ingestor = ingestor
        self.map_chunk_tokens = map_chunk_tokens
        self.digest_max_tokens = digest_max_tokens
        self.large_event_threshold_tokens = large_event_threshold_tokens
        self.max_reduce_rounds = max_reduce_rounds

    def should_digest(self, text: str) -> bool:
        """True when the event is too large to enter the main window as-is."""
        return count_text_tokens(text or "") > self.large_event_threshold_tokens

    def digest(
        self,
        text: str,
        title: Optional[str] = None,
        source: str = SOURCE_USER_INPUT,
        timestamp: Any = None,
        session_id: Optional[str] = None,
        turn_id: Optional[str] = None,
        speaker: Optional[str] = None,
    ) -> str:
        """Stores the raw text to Layer 1 (when an ingestor is wired) and
        returns a digest bounded by digest_max_tokens, framed so the model
        knows the verbatim record exists and is retrievable."""
        text = (text or "").strip()
        if not text:
            return ""

        stored_chunk_count = 0
        if self._ingestor is not None:
            stored_chunk_count = len(self._ingestor.add_event(
                text,
                source=source,
                timestamp=timestamp,
                session_id=session_id,
                turn_id=turn_id,
                speaker=speaker,
            ))

        # Map: one independent LLM call per section, each in its own
        # context window. Per-section word target splits the digest budget
        # across sections but never drops below a floor that a coherent
        # summary needs.
        sections = chunk_text(text, self.map_chunk_tokens)
        per_section_words = max(
            int(self.digest_max_tokens * 0.7 / max(1, len(sections))), 100
        )
        section_summaries: List[str] = []
        for index, section in enumerate(sections):
            prompt = _MAP_PROMPT.format(target_words=per_section_words, section=section)
            try:
                summary = self.llm(prompt).strip()
            except Exception as e:
                logger.warning(
                    "Map summarization failed for section %d/%d, using extractive head: %s",
                    index + 1, len(sections), e,
                )
                summary = ""
            if not summary:
                summary = self._extractive_head(section, int(per_section_words * 1.3))
            section_summaries.append(summary)

        combined = "\n\n".join(section_summaries)

        # Reduce: merge section summaries until they fit the digest budget.
        target_words = int(self.digest_max_tokens * 0.7)
        rounds = 0
        while count_text_tokens(combined) > self.digest_max_tokens and rounds < self.max_reduce_rounds:
            prompt = _REDUCE_PROMPT.format(target_words=target_words, summaries=combined)
            try:
                reduced = self.llm(prompt).strip()
            except Exception as e:
                logger.warning("Reduce summarization failed, falling back to truncation: %s", e)
                break
            if not reduced or count_text_tokens(reduced) >= count_text_tokens(combined):
                break
            combined = reduced
            rounds += 1

        if count_text_tokens(combined) > self.digest_max_tokens:
            combined = self._extractive_head(combined, self.digest_max_tokens)

        label = f" '{title}'" if title else ""
        if stored_chunk_count:
            provenance = (
                f"stored verbatim in memory as {stored_chunk_count} chunk(s); "
                f"exact passages are retrievable on request"
            )
        else:
            provenance = "summarized below"
        return f"[DOCUMENT DIGEST{label}: {provenance}]\n{combined}"

    @staticmethod
    def _extractive_head(text: str, max_tokens: int) -> str:
        """LLM-free fallback: the leading sentences that fit max_tokens."""
        pieces = chunk_text(text, max_tokens)
        return pieces[0] if pieces else ""

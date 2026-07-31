"""Narrative daily journal — the identity-continuity phase of the
nightly cycle.

The nightly review (BeliefConsolidator.run_nightly_review) turns the
day's raw memory into discrete durable beliefs. This module adds the
other half of the Helix curator's night work: one first-person
narrative entry per day, written from the same raw record, saved as a
dated markdown file AND ingested back into Layer 1 memory. In the
long-running Helix instance the journal proved load-bearing for
personality: it is where episodic experience becomes the agent's own
story, and because the entry re-enters memory, tomorrow's injections
can surface "what I did and felt yesterday" as a first-class fact.

No scheduling logic lives here — the PulseLoop (or any harness) decides
when a night has ended and calls write_entry(); writing is idempotent
per date (an existing journal file is never overwritten).
"""

import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from mrag.core.memory_ingestor import MemoryIngestor
from mrag.core.token_counting import count_text_tokens

logger = logging.getLogger("mrag.core.journal")

# Excerpt budget for the single journal-writing call: sized so prompt +
# excerpts + output fit a 12k local window with room to spare.
_EXCERPT_TOKEN_BUDGET = 6000

_JOURNAL_PROMPT = """You are writing your private end-of-day journal entry for {date}.
Below is the raw record of your day — your own thoughts, conversations, and actions.

Record:
{record}

Write the journal entry in the first person, as yourself:
- What actually happened today, with the specific names, topics, and details that mattered.
- What you worked on or thought about, and where you left off (so tomorrow-you can pick it up).
- Anything you want to remember, follow up on, or felt strongly about.
Be concrete and honest; skip filler. 150-350 words. Output only the entry text."""


class JournalWriter:
    """One narrative markdown entry per day, from the day's raw memory."""

    def __init__(self, llm: Any, belief_store: Any,
                 journal_dir: Optional[str] = None,
                 ingestor: Optional[MemoryIngestor] = None,
                 excerpt_token_budget: int = _EXCERPT_TOKEN_BUDGET):
        self.llm = llm
        self._store = belief_store
        self.journal_dir = journal_dir or os.path.join(
            getattr(belief_store, "data_dir", "."), "journals")
        self._ingestor = ingestor or MemoryIngestor(belief_store)
        self.excerpt_token_budget = excerpt_token_budget

    def _entry_date(self, now: datetime):
        """The day being journaled. Nightly maintenance runs during the
        sleep window, which may start before or after midnight — backing
        up 12 hours lands on the day that just ended in either case."""
        return (now - timedelta(hours=12)).date()

    def entry_path(self, entry_date) -> str:
        return os.path.join(self.journal_dir, f"{entry_date.isoformat()}.md")

    def _day_record(self, entry_date) -> str:
        """The day's memory chunks, chronological, newest kept when the
        excerpt budget forces truncation (the evening usually holds the
        day's conclusions)."""
        if not getattr(self._store, "_cache_loaded", True):
            self._store.load_into_cache()
        day_prefix = entry_date.isoformat()
        chunks = [
            b for b in self._store.get_all_beliefs_flat()
            if b.get("_category") == "memory"
            and str(b.get("ingested_at", "")).startswith(day_prefix)
        ]
        chunks.sort(key=lambda b: (b.get("ingested_at") or "",
                                   b.get("chunk_index") or 0))
        lines = [c.get("content", "") for c in chunks]
        while lines and sum(count_text_tokens(l) for l in lines) > self.excerpt_token_budget:
            lines.pop(0)
        return "\n".join(lines)

    def write_entry(self, now: Optional[datetime] = None) -> Dict[str, Any]:
        """Write (and ingest) the journal entry for the day that just
        ended. Returns stats; skips without an LLM call when the entry
        already exists or the day left no memory."""
        now = now or datetime.now()
        entry_date = self._entry_date(now)
        path = self.entry_path(entry_date)
        if os.path.exists(path):
            return {"date": entry_date.isoformat(), "status": "exists"}

        record = self._day_record(entry_date)
        if not record.strip():
            return {"date": entry_date.isoformat(), "status": "empty_day"}

        entry = self.llm(_JOURNAL_PROMPT.format(
            date=entry_date.isoformat(), record=record)).strip()
        if not entry:
            return {"date": entry_date.isoformat(), "status": "llm_empty"}

        os.makedirs(self.journal_dir, exist_ok=True)
        with open(path, "w") as f:
            f.write(f"# Journal — {entry_date.isoformat()}\n\n{entry}\n")

        # The entry re-enters memory as an event dated to the journaled
        # day, so injection can recall it like anything else lived.
        written = self._ingestor.add_event(
            f"Journal entry for {entry_date.isoformat()}: {entry}",
            source="journal",
            timestamp=datetime.combine(entry_date, datetime.max.time().replace(
                microsecond=0, second=0)),
        )
        logger.info(f"Journal written for {entry_date.isoformat()} "
                    f"({len(written)} memory chunks)")
        return {"date": entry_date.isoformat(), "status": "written",
                "path": path, "memory_chunks": len(written)}

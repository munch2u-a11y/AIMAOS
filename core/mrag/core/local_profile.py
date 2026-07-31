"""Budget derivation for small-context local models.

Running mRAG under a consumer-grade local model (4-9B parameters, a 12-16k
context window) inverts the usual proportions: the window is the scarce
resource and the memory system carries coherence instead of raw context.
Because Layer 1 stores every turn verbatim, aggressively shrinking the
active window costs no information — anything evicted stays retrievable.

LocalAgentProfile derives every budget from a single user-set
context_token_limit so the pieces stay in ratio as the window changes:

- Compression triggers at 75% of the window (vs. the 65% default), and the
  rolling summary carries a hard cap so it can't grow to eat the space it
  is supposed to free.
- The injection ceiling is an absolute slim cap (~6% of the window,
  clamped to 400-700 tokens — the band the injector's dynamic budget
  already produces on big models) so injections stay a fixed small tax
  per turn. Empirically (LoCoMo evidence-recall sweep) a 700 cap is
  accuracy-neutral versus the uncapped budget.
- Events larger than ~15% of the window are routed through the
  DocumentDigester: raw text to Layer 1 verbatim, and only a bounded
  digest — produced by the same local model in separate throwaway
  contexts — enters the main window.

The default 12k window budgets roughly like this at the 9.2k trigger:
head (protected) + one summary (≤1.2k) + injection (≤0.7k) leaves ~7k of
free conversation space — 10-20 medium exchanges before a compression
cycle, and never fewer than ~5 even with long-winded turns.
"""

from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from mrag.core.context_compressor import ContextCompressor
from mrag.core.document_digester import DocumentDigester
from mrag.core.memory_ingestor import MemoryIngestor, DEFAULT_CHUNK_TOKENS
from mrag.core.pre_generative_injection import PreGenerativeInjector
from mrag.memory.belief_store import BeliefStore
from mrag.core.vector_store import VectorStore


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


@dataclass
class LocalAgentProfile:
    """One knob (context_token_limit) → every mRAG budget, in ratio.

    Every derived field can be overridden explicitly; None means "derive".
    """

    context_token_limit: int = 12288
    compress_threshold_percent: float = 0.75

    # Derived unless set.
    max_injected_tokens: Optional[int] = None
    summary_max_tokens: Optional[int] = None
    large_event_threshold_tokens: Optional[int] = None
    map_chunk_tokens: Optional[int] = None
    digest_max_tokens: Optional[int] = None

    protect_first_n: int = 1
    tail_max_messages: int = 8
    tail_token_fraction: float = 0.10
    memory_chunk_tokens: int = DEFAULT_CHUNK_TOKENS

    def __post_init__(self):
        limit = self.context_token_limit
        if limit < 4096:
            raise ValueError(
                "LocalAgentProfile needs at least a 4096-token window: below "
                "that the trigger threshold can't hold the protected head, a "
                "summary, an injection, and even one full exchange at once."
            )
        if self.max_injected_tokens is None:
            # Slim absolute cap: ~6% of the window, clamped to 400-700.
            # Calibrated on LoCoMo evidence-recall sweeps (see
            # tests/injection_budget_comparison.py): the default dynamic
            # budget settles around ~730 injected tokens, a 700 cap costs
            # under one point of evidence recall, and recall falls off
            # steeply below ~500 — so windows >=12k take the full 700 and
            # smaller windows trade recall for space explicitly.
            self.max_injected_tokens = _clamp(round(limit * 0.06), 400, 700)
        if self.summary_max_tokens is None:
            self.summary_max_tokens = round(limit * 0.10)
        if self.large_event_threshold_tokens is None:
            self.large_event_threshold_tokens = round(limit * 0.15)
        if self.map_chunk_tokens is None:
            # One digester map call = section + prompt scaffolding + output;
            # ~25% of the window keeps that comfortably inside one context.
            self.map_chunk_tokens = round(limit * 0.25)
        if self.digest_max_tokens is None:
            self.digest_max_tokens = _clamp(round(limit * 0.07), 300, 900)

    @property
    def compress_trigger_tokens(self) -> int:
        return int(self.context_token_limit * self.compress_threshold_percent)

    def estimate_turn_capacity(self, avg_turn_tokens: int, head_tokens: int = 0) -> int:
        """Exchanges that fit between compressions in steady state: the
        trigger threshold minus the protected head, one standing rolling
        summary, and one standing injection, divided by the cost of an
        average exchange (user turn + assistant turn)."""
        overhead = head_tokens + (self.summary_max_tokens or 0) + (self.max_injected_tokens or 0)
        usable = self.compress_trigger_tokens - overhead
        return max(0, usable // max(1, avg_turn_tokens))

    # --- Component builders -------------------------------------------------

    def build_compressor(self, llm_callable: Callable[[str], str]) -> ContextCompressor:
        return ContextCompressor(
            llm_callable=llm_callable,
            context_token_limit=self.context_token_limit,
            threshold_percent=self.compress_threshold_percent,
            protect_first_n=self.protect_first_n,
            summary_max_tokens=self.summary_max_tokens,
            tail_max_messages=self.tail_max_messages,
            tail_token_fraction=self.tail_token_fraction,
        )

    def build_injector(
        self,
        belief_store: BeliefStore,
        vector_store: VectorStore,
        **kwargs: Any,
    ) -> PreGenerativeInjector:
        kwargs.setdefault("max_injected_tokens", self.max_injected_tokens)
        return PreGenerativeInjector(
            belief_store=belief_store,
            vector_store=vector_store,
            **kwargs,
        )

    def build_ingestor(self, belief_store: BeliefStore) -> MemoryIngestor:
        return MemoryIngestor(belief_store, chunk_tokens=self.memory_chunk_tokens)

    def build_digester(
        self,
        llm_callable: Callable[[str], str],
        ingestor: Optional[MemoryIngestor] = None,
    ) -> DocumentDigester:
        return DocumentDigester(
            llm_callable=llm_callable,
            ingestor=ingestor,
            map_chunk_tokens=self.map_chunk_tokens,
            digest_max_tokens=self.digest_max_tokens,
            large_event_threshold_tokens=self.large_event_threshold_tokens,
        )

    def describe(self) -> Dict[str, Any]:
        """The resolved budget table, for logging/debugging a deployment."""
        return {
            "context_token_limit": self.context_token_limit,
            "compress_trigger_tokens": self.compress_trigger_tokens,
            "compress_threshold_percent": self.compress_threshold_percent,
            "max_injected_tokens": self.max_injected_tokens,
            "summary_max_tokens": self.summary_max_tokens,
            "large_event_threshold_tokens": self.large_event_threshold_tokens,
            "map_chunk_tokens": self.map_chunk_tokens,
            "digest_max_tokens": self.digest_max_tokens,
            "tail_max_messages": self.tail_max_messages,
            "tail_token_fraction": self.tail_token_fraction,
            "protect_first_n": self.protect_first_n,
            "memory_chunk_tokens": self.memory_chunk_tokens,
        }

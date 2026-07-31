"""Plain-text terminal dashboard for a local mRAG agent.

One `render()` call returns a compact, human-readable status panel —
context-window pressure, distance to the next compression, memory store
size, injection/summary budgets, and subagent tool activity. Pure string
building on data the components already expose: no HTML, no server, no
dependencies, no LLM calls. Print it between turns, or run it under
`watch`-style loops.

ANSI color is used only when stdout is a TTY (or when forced via the
`color` argument); piped output stays clean.
"""

import os
import sys
from typing import Any, Dict, List, Optional

from mrag.core.token_counting import count_text_tokens

_RESET = "\x1b[0m"
_DIM = "\x1b[2m"
_GREEN = "\x1b[32m"
_YELLOW = "\x1b[33m"
_RED = "\x1b[31m"

PANEL_WIDTH = 64
BAR_WIDTH = 24


def _fmt(n: Optional[float]) -> str:
    if n is None:
        return "?"
    return f"{int(n):,}"


class MemoryDashboard:
    """Renders agent/memory status as a terminal panel.

    Every component is optional — the panel shows what it's given and
    omits the rest, so it works for injection-only setups as well as a
    fully wired local agent.
    """

    def __init__(
        self,
        profile=None,            # LocalAgentProfile
        belief_store=None,       # BeliefStore
        compressor=None,         # ContextCompressor
        injector=None,           # PreGenerativeInjector
        llm=None,                # LocalLLM (llm_detector) or any object/str
        tool_runner=None,        # SubAgentToolRunner
        title: str = "mRAG Local Agent",
    ):
        self.profile = profile
        self.belief_store = belief_store
        self.compressor = compressor
        self.injector = injector
        self.llm = llm
        self.tool_runner = tool_runner
        self.title = title

    # -- data collection ------------------------------------------------------

    def snapshot(self, messages: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """The raw numbers behind the panel, for programmatic use."""
        snap: Dict[str, Any] = {}

        limit = None
        trigger = None
        if self.profile is not None:
            limit = self.profile.context_token_limit
            trigger = self.profile.compress_trigger_tokens
        elif self.compressor is not None:
            limit = self.compressor.context_token_limit
            trigger = self.compressor.threshold_tokens
        snap["context_limit"] = limit
        snap["compress_trigger"] = trigger

        if messages is not None:
            snap["context_tokens"] = sum(
                count_text_tokens(str(m.get("content", ""))) for m in messages
            )
            snap["message_count"] = len(messages)

        if self.llm is not None:
            describe = getattr(self.llm, "describe", None)
            snap["llm"] = describe() if callable(describe) else {"model": str(self.llm)}

        if self.belief_store is not None:
            try:
                beliefs = self.belief_store.get_all_beliefs_flat()
                snap["memory_chunks"] = sum(1 for b in beliefs if b.get("_category") == "memory")
                snap["beliefs"] = sum(
                    1 for b in beliefs
                    if b.get("_category") not in ("memory", "concepts")
                )
                data_dir = getattr(self.belief_store, "data_dir", None)
                if data_dir and os.path.isdir(data_dir):
                    snap["store_bytes"] = sum(
                        os.path.getsize(os.path.join(root, f))
                        for root, _, files in os.walk(data_dir) for f in files
                    )
            except Exception:
                pass

        if self.injector is not None:
            snap["last_injection_tokens"] = getattr(self.injector, "last_injection_tokens", 0)
            snap["injection_cap"] = getattr(self.injector, "max_injected_tokens", None)

        if self.compressor is not None:
            snap["compressions"] = getattr(self.compressor, "compression_count", 0)
            summary = getattr(self.compressor, "_previous_summary", None)
            snap["summary_tokens"] = count_text_tokens(summary) if summary else 0
            snap["summary_cap"] = getattr(self.compressor, "summary_max_tokens", None)

        if self.tool_runner is not None:
            snap["tool_stats"] = dict(self.tool_runner.stats)
            snap["tool_groups"] = {
                name: len(self.tool_runner.registry.get(name).tools)
                for name in self.tool_runner.registry.group_names()
            }

        return snap

    # -- rendering ------------------------------------------------------------

    def render(self, messages: Optional[List[Dict[str, Any]]] = None,
               color: Optional[bool] = None) -> str:
        snap = self.snapshot(messages)
        if color is None:
            color = sys.stdout.isatty()

        def paint(text: str, code: str) -> str:
            return f"{code}{text}{_RESET}" if color else text

        rows: List[str] = []

        llm_info = snap.get("llm")
        if llm_info:
            model = llm_info.get("model", "?")
            provider = llm_info.get("provider", "")
            base = llm_info.get("base_url", "")
            detail = f" via {provider} ({base})" if provider else ""
            rows.append(("Model", f"{model}{detail}"))

        limit = snap.get("context_limit")
        trigger = snap.get("compress_trigger")
        if limit:
            pct = f" ({int(trigger / limit * 100)}%)" if trigger else ""
            rows.append(("Window", f"{_fmt(limit)} tokens · compression at {_fmt(trigger)}{pct}"))

        tokens = snap.get("context_tokens")
        if tokens is not None and limit:
            ratio = min(1.0, tokens / limit)
            filled = int(round(ratio * BAR_WIDTH))
            bar = "█" * filled + "░" * (BAR_WIDTH - filled)
            code = _GREEN if trigger and tokens < trigger * 0.75 else (
                _YELLOW if trigger and tokens < trigger else _RED)
            rows.append(("Context", f"{paint(bar, code)}  {_fmt(tokens)} / {_fmt(limit)} ({int(ratio * 100)}%)"))
            if trigger and tokens < trigger:
                exchange = 600  # medium exchange heuristic, matches profile docs
                rows.append(("", f"~{max(0, (trigger - tokens) // exchange)} medium exchanges until compression"))
            elif trigger:
                rows.append(("", "compression due on next check"))

        if "memory_chunks" in snap:
            mem = f"{_fmt(snap['memory_chunks'])} raw chunks · {_fmt(snap.get('beliefs', 0))} beliefs"
            if "store_bytes" in snap:
                mem += f" · {snap['store_bytes'] / 1_048_576:.1f} MB on disk"
            rows.append(("Memory", mem))

        if "last_injection_tokens" in snap:
            cap = snap.get("injection_cap")
            cap_str = f" (cap {_fmt(cap)})" if cap else ""
            line = f"last {_fmt(snap['last_injection_tokens'])} tok{cap_str}"
            if "summary_tokens" in snap:
                s_cap = snap.get("summary_cap")
                s_cap_str = f" (cap {_fmt(s_cap)})" if s_cap else ""
                line += f" · summary {_fmt(snap['summary_tokens'])} tok{s_cap_str}"
            rows.append(("Inject", line))

        if "compressions" in snap:
            n = snap["compressions"]
            rows.append(("Cycles", f"{n} compression{'s' if n != 1 else ''} this session"))

        if "tool_groups" in snap:
            groups = " ".join(f"{g}({n})" for g, n in snap["tool_groups"].items()) or "none"
            stats = snap.get("tool_stats", {})
            line = f"{groups} · {stats.get('runs', 0)} subagent runs"
            if stats.get("learned"):
                line += f" · {stats['learned']} learned"
            if stats.get("last_group"):
                line += f" · last: {stats['last_group']} {stats.get('last_status') or ''}".rstrip()
            rows.append(("Tools", line))

        # Frame it.
        label_width = 8
        body_width = PANEL_WIDTH - 4
        top = f"┌─ {self.title} " + "─" * max(1, PANEL_WIDTH - len(self.title) - 5) + "┐"
        lines = [top]
        for label, value in rows:
            text = f"{label:<{label_width}}{value}"
            visible = _visible_len(text)
            if visible > body_width and "\x1b" not in text:
                text = text[: body_width - 1] + "…"
                visible = body_width
            pad = max(0, body_width - visible)
            lines.append(f"│ {text}{' ' * pad} │")
        lines.append("└" + "─" * (PANEL_WIDTH - 2) + "┘")
        return "\n".join(lines)


def _visible_len(text: str) -> int:
    """Length ignoring ANSI escape sequences."""
    import re
    return len(re.sub(r"\x1b\[[0-9;]*m", "", text))

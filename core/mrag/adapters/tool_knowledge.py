"""Per-tool micro belief formation and schema self-improvement.

After each subagent tool run, a micro consolidation pass (one LLM call in
its own throwaway context, same local model) reviews the run's transcript
and extracts durable *operational* knowledge about the tools themselves —
argument quirks, response shapes, failure modes, effective strategies.
Task-specific content facts are explicitly excluded here: those already
flow into Layer 1 memory via the runner's observation ingestion.

Statements are stored as 'skills' beliefs scoped to their tool and pushed
through BeliefStore.merge_or_add_belief, so the store's existing evidence
mechanics apply unchanged: a statement re-learned across runs is
corroborated (verifications +1, confidence up), a contradicted one is
superseded. "Density" is therefore measured, not guessed — verifications
count how many independent runs re-derived the same statement.

The densest statements are promoted into the tool schema itself: once a
statement crosses the verification threshold, `promoted_statements()`
returns it and the ToolGroupRegistry appends it to that tool's manifest
entry, so every future subagent starts with what its predecessors learned
(the Helix-agi pattern).
"""

import hashlib
import json
import logging
import re
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

from mrag._compat import np
from mrag.core.token_counting import count_text_tokens
from mrag.memory.belief_store import BeliefStore

logger = logging.getLogger("mrag.adapters.tool_knowledge")

TOOL_KNOWLEDGE_SOURCE = "tool_learning"

# Corroboration thresholds for re-derived statements about the same tool.
# Deliberately NOT BeliefStore.merge_or_add_belief: its contradiction
# heuristic (both sides carry unique salient tokens => value swap =>
# evidence reset) is right for facts like "prefers Python" vs "prefers
# Rust" but wrong here — two independently worded derivations of the same
# tool quirk are corroboration, and resetting verifications on every
# rewording would keep knowledge permanently below the promotion bar.
CORROBORATION_JACCARD = 0.5
CORROBORATION_COSINE = 0.82

_CONTENT_WORD_RE = re.compile(r"[a-z0-9]{3,}")
_MATCH_STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "are", "was",
    "when", "then", "than", "rather", "just", "must", "should", "can",
    "will", "its", "has", "have", "been", "being", "not", "use", "used",
    "using", "instead", "also", "only",
}


def _content_tokens(text: str) -> set:
    """Lightly stemmed content words, for restatement matching. Unlike the
    store's _salient_tokens (digits + capitalized values, for contradiction
    detection), this captures the full operational vocabulary of a
    plain-English statement."""
    tokens = set()
    for word in _CONTENT_WORD_RE.findall(text.lower()):
        if word in _MATCH_STOPWORDS:
            continue
        if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
            word = word[:-1]
        tokens.add(word)
    return tokens

_EXTRACTION_PROMPT = """Below is one completed run of a tool-using agent. Extract durable knowledge about the TOOLS themselves.

TOOLS AVAILABLE: {tool_names}
TASK GIVEN: {task}

TOOL CALLS AND RETURNS:
{calls}

FINAL REPORT: {report}

Extract 0-3 short statements of operational knowledge about how these tools behave or are best used — argument formats, response shape, quirks, failure modes, effective strategies. Rules:
- Only knowledge that would help a FUTURE run of a DIFFERENT task.
- Never include task-specific content facts (names, numbers, dates, results).
- One sentence per statement.
Output a JSON array like [{{"tool": "<tool name>", "statement": "<sentence>"}}] and nothing else. Output [] if nothing durable was learned."""

_JSON_ARRAY_RE = re.compile(r'\[.*\]', re.DOTALL)


def _parse_json_array(text: str) -> Optional[List[Dict[str, Any]]]:
    m = _JSON_ARRAY_RE.search(text or "")
    if not m:
        return None
    candidate = m.group(0)
    depth = 0
    for i, ch in enumerate(candidate):
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                candidate = candidate[: i + 1]
                break
    try:
        parsed = json.loads(candidate)
        return parsed if isinstance(parsed, list) else None
    except json.JSONDecodeError:
        return None


class ToolKnowledgeConsolidator:
    """Micro belief pass per subagent run + schema promotion."""

    def __init__(
        self,
        llm_callable: Callable[[str], str],
        belief_store: BeliefStore,
        vector_store: Optional[Any] = None,
        max_statements_per_run: int = 3,
        promotion_min_verifications: float = 2.0,
        promotion_top_k: int = 3,
        promotion_max_tokens: int = 120,
    ):
        """
        Args:
            llm_callable: The same local model; each extraction is one
                independent call in a fresh context.
            vector_store: Optional — enables semantic dedup of restated
                knowledge in merge_or_add_belief; without it the template
                channel still catches same-slot restatements.
            promotion_min_verifications: A statement must be re-derived by
                at least this many runs before it's trusted enough to enter
                the tool schema (2.0 = seen in two independent runs).
            promotion_top_k / promotion_max_tokens: Per-tool caps on how
                much learned text a manifest entry may carry — the schema
                must stay schema-sized.
        """
        self.llm = llm_callable
        self._store = belief_store
        self._vector_store = vector_store
        self.max_statements_per_run = max_statements_per_run
        self.promotion_min_verifications = promotion_min_verifications
        self.promotion_top_k = promotion_top_k
        self.promotion_max_tokens = promotion_max_tokens

    # -- formation -------------------------------------------------------

    def learn_from_run(
        self,
        group_name: str,
        valid_tool_names: List[str],
        task: str,
        tool_calls: List[Tuple[str, str, str]],
        report: str,
    ) -> int:
        """Runs the micro consolidation pass over one completed subagent
        run. tool_calls entries are (tool_name, args_json, observation).
        Returns the number of statements recorded (new or corroborated)."""
        if not tool_calls:
            return 0

        calls_text = "\n\n".join(
            f"{name}({args}) -> {obs}" for name, args, obs in tool_calls
        )
        prompt = _EXTRACTION_PROMPT.format(
            tool_names=", ".join(valid_tool_names),
            task=task,
            calls=calls_text,
            report=report,
        )
        try:
            output = self.llm(prompt)
        except Exception as e:
            logger.warning("Tool-knowledge extraction call failed: %s", e)
            return 0

        entries = _parse_json_array(output) or []
        recorded = 0
        for entry in entries[: self.max_statements_per_run]:
            if not isinstance(entry, dict):
                continue
            tool_name = str(entry.get("tool", "")).strip()
            statement = str(entry.get("statement", "")).strip().rstrip(".")
            if not statement or tool_name not in valid_tool_names:
                continue
            if self._record(group_name, tool_name, statement):
                recorded += 1
        return recorded

    def _record(self, group_name: str, tool_name: str, statement: str) -> bool:
        # The tool name is prefixed into the content so the statement is
        # self-describing if normal retrieval ever injects it.
        content = f"{tool_name}: {statement}."

        new_embedding = None
        if self._vector_store is not None:
            try:
                new_embedding = self._vector_store.embed_text(content)
            except Exception as e:
                logger.warning("Tool-knowledge embedding failed: %s", e)

        # Corroboration is scoped to this tool's own statements: a
        # restated quirk (matched by shared salient tokens or embedding
        # similarity) strengthens the existing belief's evidence rather
        # than adding a near-duplicate.
        existing = self._find_corroborated(group_name, tool_name, content, new_embedding)
        if existing is not None:
            existing["verifications"] = existing.get("verifications", 1.0) + 1.0
            confidence = existing.get("confidence", 0.5)
            existing["confidence"] = min(1.0, confidence + (1.0 - confidence) * 0.2)
            existing["last_accessed"] = datetime.now().isoformat()
            self._store.update_belief("skills", existing)
            return True

        digest = hashlib.sha256(
            f"{group_name}|{tool_name}|{statement.lower()}".encode("utf-8")
        ).hexdigest()[:12]
        belief_id = f"toolk_{digest}"
        added = self._store.add_belief(
            category="skills",
            belief_id=belief_id,
            content=content,
            confidence=0.6,
            source=TOOL_KNOWLEDGE_SOURCE,
            tool_name=tool_name,
            group_name=group_name,
        )
        # Cache the embedding immediately so the next run's corroboration
        # check can compare against it without waiting for an index sync.
        if added and new_embedding is not None:
            belief = self._store._beliefs_cache.get(belief_id)
            if belief is not None:
                belief["embedding"] = new_embedding.tolist()
                try:
                    self._vector_store.add_vectors(
                        [belief_id], [new_embedding], [{"category": "skills"}])
                except Exception as e:
                    logger.warning("Tool-knowledge indexing failed: %s", e)
        return added

    def _find_corroborated(self, group_name: str, tool_name: str, content: str,
                           new_embedding) -> Optional[Dict[str, Any]]:
        """The existing statement (same tool, same group) that `content`
        restates, or None. Content-word overlap catches shared-vocabulary
        rewordings; embedding cosine catches full paraphrases."""
        new_tokens = _content_tokens(content)
        for belief in self._store._beliefs_cache.values():
            if belief.get("_category") != "skills":
                continue
            if belief.get("tool_name") != tool_name or belief.get("group_name") != group_name:
                continue
            if TOOL_KNOWLEDGE_SOURCE not in str(belief.get("source", "")):
                continue

            cand_tokens = _content_tokens(belief.get("content", ""))
            union = new_tokens | cand_tokens
            if union and len(new_tokens & cand_tokens) / len(union) >= CORROBORATION_JACCARD:
                return belief

            cand_embedding = belief.get("embedding")
            if new_embedding is not None and cand_embedding and self._vector_store is not None:
                similarity = self._vector_store.cosine_similarity(
                    new_embedding, np.array(cand_embedding, dtype=np.float32))
                if similarity >= CORROBORATION_COSINE:
                    return belief
        return None

    # -- promotion -------------------------------------------------------

    def promoted_statements(self, group_name: str) -> Dict[str, List[str]]:
        """tool_name -> the densest, most-relied-on statements for that
        tool: verification count >= threshold, ranked by (verifications,
        confidence), capped per tool by count and tokens."""
        if not self._store._cache_loaded:
            self._store.load_into_cache()

        by_tool: Dict[str, List[Dict[str, Any]]] = {}
        for belief in self._store._beliefs_cache.values():
            if belief.get("_category") != "skills":
                continue
            if TOOL_KNOWLEDGE_SOURCE not in str(belief.get("source", "")):
                continue
            if belief.get("group_name") != group_name:
                continue
            if belief.get("verifications", 0) < self.promotion_min_verifications:
                continue
            tool_name = belief.get("tool_name")
            if tool_name:
                by_tool.setdefault(tool_name, []).append(belief)

        promoted: Dict[str, List[str]] = {}
        for tool_name, beliefs in by_tool.items():
            beliefs.sort(
                key=lambda b: (b.get("verifications", 0), b.get("confidence", 0)),
                reverse=True,
            )
            statements: List[str] = []
            spent = 0
            for belief in beliefs[: self.promotion_top_k]:
                content = belief.get("content", "")
                # Strip the "tool_name: " prefix — the manifest renders the
                # statement under the tool's own heading already.
                if content.lower().startswith(tool_name.lower() + ":"):
                    content = content[len(tool_name) + 1:].strip()
                tokens = count_text_tokens(content)
                if statements and spent + tokens > self.promotion_max_tokens:
                    break
                statements.append(content)
                spent += tokens
            if statements:
                promoted[tool_name] = statements
        return promoted

    def learned_statement_count(self) -> int:
        """Total tool-knowledge statements in the store (for the dashboard)."""
        if not self._store._cache_loaded:
            self._store.load_into_cache()
        return sum(
            1 for b in self._store._beliefs_cache.values()
            if b.get("_category") == "skills"
            and TOOL_KNOWLEDGE_SOURCE in str(b.get("source", ""))
        )

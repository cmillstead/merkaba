# src/merkaba/memory/retrieval.py
import logging
from dataclasses import dataclass, field
from typing import Any

from merkaba.memory.store import MemoryStore

logger = logging.getLogger(__name__)

try:
    from merkaba.memory.vectors import VectorMemory

    HAS_VECTORS = True
except ImportError:
    HAS_VECTORS = False


@dataclass
class RetrievalConfig:
    """Tuning knobs for memory retrieval."""

    max_items: int = 5
    min_relevance_score: float = 0.25  # keyword overlap ratio 0.0–1.0
    max_distance: float = 1.5  # ChromaDB L2 threshold
    max_context_tokens: int = 800  # ~3200 chars at 4 chars/token


@dataclass
class MemoryRetrieval:
    """Unified query interface combining SQLite and vector search."""

    store: MemoryStore
    vectors: Any = field(default=None)
    config: RetrievalConfig = field(default_factory=RetrievalConfig)

    def recall(
        self, query: str, business_id: int | None = None, limit: int | None = None
    ) -> list[dict[str, Any]]:
        """Semantic search across facts, decisions, learnings, and episodes.

        Returns results hydrated from SQLite with vector similarity scores.
        Falls back to keyword search if vectors unavailable.
        """
        effective_limit = limit if limit is not None else self.config.max_items
        logger.debug("recall: vectors=%s, query=%s", self.vectors is not None, query[:50])
        if self.vectors:
            results = self._recall_semantic(query, business_id, effective_limit)
            # Keyword safety net: backfill with keyword hits not already found
            if len(results) < effective_limit:
                seen_ids = {
                    (r.get("type"), r.get("id"))
                    for r in results
                    if r.get("id") is not None
                }
                keyword_results = self._recall_keyword(
                    query, business_id, effective_limit
                )
                for kr in keyword_results:
                    if len(results) >= effective_limit:
                        break
                    if (kr.get("type"), kr.get("id")) not in seen_ids:
                        results.append(kr)
        else:
            results = self._recall_keyword(query, business_id, effective_limit)

        # Append recent episodes
        episodes = self._recall_episodes(business_id)
        results.extend(episodes)

        # Track access for returned results
        self._track_access(results)

        return self._apply_token_budget(results)

    # ------------------------------------------------------------------
    # Keyword search
    # ------------------------------------------------------------------

    def _keyword_score(self, query_words: list[str], text: str) -> float:
        """Score a text against query words by word overlap ratio."""
        if not query_words:
            return 0.0
        text_lower = text.lower()
        matched = sum(1 for w in query_words if w in text_lower)
        return matched / len(query_words)

    def _recall_keyword(
        self, query: str, business_id: int | None, limit: int
    ) -> list[dict[str, Any]]:
        """Fallback keyword search when vectors are unavailable."""
        scored: list[tuple[float, dict[str, Any]]] = []
        query_lower = query.lower()
        query_words = query_lower.split()

        # Search facts across specified business or all businesses
        business_ids = (
            [business_id] if business_id else [b["id"] for b in self.store.list_businesses()]
        )
        logger.debug("_recall_keyword: business_ids=%s", business_ids)
        for bid in business_ids:
            facts = self.store.get_facts(bid)
            logger.debug("business %s: %d facts", bid, len(facts))
            for fact in facts:
                text = f"{fact['category']} {fact['key']} {fact['value']}"
                score = self._keyword_score(query_words, text)
                if score >= self.config.min_relevance_score:
                    scored.append((score, {"type": "fact", "score": score, **fact}))

            decisions = self.store.get_decisions(bid)
            for d in decisions:
                text = f"{d['decision']} {d['reasoning']}"
                score = self._keyword_score(query_words, text)
                if score >= self.config.min_relevance_score:
                    scored.append((score, {"type": "decision", "score": score, **d}))

        learnings = self.store.get_learnings()
        for l in learnings:
            score = self._keyword_score(query_words, l["insight"])
            if score >= self.config.min_relevance_score:
                scored.append((score, {"type": "learning", "score": score, **l}))

        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [item for _, item in scored[:limit]]

    # ------------------------------------------------------------------
    # Semantic (vector) search
    # ------------------------------------------------------------------

    def _recall_semantic(
        self, query: str, business_id: int | None, limit: int
    ) -> list[dict[str, Any]]:
        results = []
        max_dist = self.config.max_distance

        fact_hits = self.vectors.search_facts(query, business_id, limit)
        for hit in fact_hits:
            dist = hit.get("distance", float("inf"))
            if dist > max_dist:
                continue
            fact = self.store.get_fact(hit["id"])
            if fact:
                score = max(0.0, 1.0 - dist / max_dist)
                results.append({
                    "type": "fact",
                    "distance": dist,
                    "score": score,
                    **fact,
                })

        decision_hits = self.vectors.search_decisions(query, business_id, limit)
        for hit in decision_hits:
            dist = hit.get("distance", float("inf"))
            if dist > max_dist:
                continue
            decisions = self.store.get_decisions(business_id or 0)
            for d in decisions:
                if d["id"] == hit["id"]:
                    score = max(0.0, 1.0 - dist / max_dist)
                    results.append({
                        "type": "decision",
                        "distance": dist,
                        "score": score,
                        **d,
                    })
                    break

        learning_hits = self.vectors.search_learnings(query, limit)
        for hit in learning_hits:
            dist = hit.get("distance", float("inf"))
            if dist > max_dist:
                continue
            learnings = self.store.get_learnings()
            for l in learnings:
                if l["id"] == hit["id"]:
                    score = max(0.0, 1.0 - dist / max_dist)
                    results.append({
                        "type": "learning",
                        "distance": dist,
                        "score": score,
                        **l,
                    })
                    break

        results.sort(key=lambda r: r.get("distance", float("inf")))
        return results[:limit]

    # ------------------------------------------------------------------
    # Episode search
    # ------------------------------------------------------------------

    def _recall_episodes(
        self, business_id: int | None, limit: int = 3
    ) -> list[dict[str, Any]]:
        """Return recent episodes formatted as recall results."""
        episodes = self.store.get_episodes(business_id=business_id, limit=limit)
        return [
            {
                "type": "episode",
                "summary": ep.get("summary", ""),
                "outcome": ep.get("outcome", ""),
                "task_type": ep.get("task_type", ""),
                "created_at": ep.get("created_at", ""),
            }
            for ep in episodes
        ]

    # ------------------------------------------------------------------
    # Access tracking
    # ------------------------------------------------------------------

    def _track_access(self, results: list[dict[str, Any]]) -> None:
        """Update last_accessed and access_count for returned results."""
        try:
            fact_ids = [r["id"] for r in results if r.get("type") == "fact"]
            decision_ids = [r["id"] for r in results if r.get("type") == "decision"]
            learning_ids = [r["id"] for r in results if r.get("type") == "learning"]
            if fact_ids:
                self.store.touch_accessed("facts", fact_ids)
            if decision_ids:
                self.store.touch_accessed("decisions", decision_ids)
            if learning_ids:
                self.store.touch_accessed("learnings", learning_ids)
        except Exception as e:
            logger.debug("Access tracking failed: %s", e)

    # ------------------------------------------------------------------
    # Token budget
    # ------------------------------------------------------------------

    @staticmethod
    def _result_to_text(r: dict[str, Any]) -> str:
        """Approximate the text representation of a result for budget estimation."""
        if r["type"] == "fact":
            return f"{r.get('category', '')}: {r.get('key', '')} = {r.get('value', '')}"
        elif r["type"] == "decision":
            return f"{r.get('decision', '')} — {r.get('reasoning', '')}"
        elif r["type"] == "learning":
            return r.get("insight", "")
        elif r["type"] == "episode":
            return f"[{r.get('task_type', '')}] {r.get('summary', '')} ({r.get('outcome', '')})"
        return ""

    def _apply_token_budget(self, results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Trim results to fit within the configured token budget."""
        budget_chars = self.config.max_context_tokens * 4  # ~4 chars per token
        total, kept = 0, []
        for r in results:
            text_len = len(self._result_to_text(r))
            if total + text_len > budget_chars and kept:
                break
            kept.append(r)
            total += text_len
        return kept

    # ------------------------------------------------------------------
    # Write helpers
    # ------------------------------------------------------------------

    def remember(
        self,
        business_id: int,
        category: str,
        key: str,
        value: str,
        confidence: int = 100,
        source: str | None = None,
    ) -> int:
        """Store a fact and index it for semantic search."""
        fact_id = self.store.add_fact(
            business_id=business_id,
            category=category,
            key=key,
            value=value,
            confidence=confidence,
            source=source,
        )
        if self.vectors:
            text = f"{category}: {key} = {value}"
            self.vectors.index_fact(fact_id, business_id, text)
        return fact_id

    def what_do_i_know(
        self, topic: str, business_id: int | None = None
    ) -> str:
        """Return a formatted summary of what Merkaba knows about a topic."""
        results = self.recall(topic, business_id, limit=10)
        if not results:
            return f"I don't have any information about '{topic}' yet."

        lines = [f"Here's what I know about '{topic}':\n"]
        for r in results:
            if r["type"] == "fact":
                lines.append(f"  [{r['category']}] {r['key']}: {r['value']}")
            elif r["type"] == "decision":
                lines.append(f"  [Decision] {r['decision']} — {r['reasoning']}")
            elif r["type"] == "learning":
                lines.append(f"  [Learning] {r['insight']}")
            elif r["type"] == "episode":
                lines.append(f"  [Episode] {r['summary']} ({r['outcome']})")
        return "\n".join(lines)

    def close(self):
        self.store.close()
        if self.vectors:
            self.vectors.close()

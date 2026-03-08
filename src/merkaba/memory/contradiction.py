# src/merkaba/memory/contradiction.py
import logging
from dataclasses import dataclass, field
from typing import Any

from merkaba.memory.store import MemoryStore

logger = logging.getLogger(__name__)


def _keyword_set(text: str) -> set[str]:
    """Extract lowercase keyword set from text, filtering short words."""
    return {w for w in text.lower().split() if len(w) > 2}


def _keyword_overlap(text_a: str, text_b: str) -> float:
    """Compute Jaccard similarity between keyword sets of two texts."""
    set_a = _keyword_set(text_a)
    set_b = _keyword_set(text_b)
    if not set_a or not set_b:
        return 0.0
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union)


@dataclass
class ContradictionDetector:
    """Detects contradictions and deduplicates memory recall results."""

    store: MemoryStore
    similarity_threshold: float = 0.85
    contradiction_threshold: float = 0.7
    _llm: Any = field(default=None, init=False, repr=False)

    def deduplicate_by_recency(self, results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Group results by keyword overlap, keep most recent per group."""
        if not results:
            return results

        groups: list[list[dict[str, Any]]] = []
        for item in results:
            text = self._item_text(item)
            placed = False
            for group in groups:
                representative_text = self._item_text(group[0])
                if _keyword_overlap(text, representative_text) >= self.similarity_threshold:
                    group.append(item)
                    placed = True
                    break
            if not placed:
                groups.append([item])

        # Keep the most recent item from each group
        deduplicated = []
        for group in groups:
            newest = max(group, key=lambda x: x.get("created_at", ""))
            deduplicated.append(newest)

        return deduplicated

    def check_on_write(
        self, business_id: int, category: str, key: str, value: str
    ) -> list[dict[str, Any]]:
        """Check if a new fact contradicts existing facts.

        Queries existing facts for the same business+category, computes keyword
        overlap, and uses the classifier model for high-overlap matches.

        Returns list of contradicted fact dicts.
        """
        existing = self.store.get_facts(business_id, category=category)
        if not existing:
            return []

        new_text = f"{key} {value}"
        candidates = []
        for fact in existing:
            existing_text = f"{fact['key']} {fact['value']}"
            overlap = _keyword_overlap(new_text, existing_text)
            if overlap >= self.contradiction_threshold:
                candidates.append(fact)

        if not candidates:
            return []

        contradicted = []
        for fact in candidates:
            if self._is_contradiction(new_text, f"{fact['key']} {fact['value']}"):
                contradicted.append(fact)

        return contradicted

    def resolve(self, contradicted_ids: list[int]) -> int:
        """Archive contradicted facts. Returns count archived."""
        count = 0
        for fact_id in contradicted_ids:
            try:
                self.store.archive("facts", fact_id)
                count += 1
            except Exception as e:
                logger.warning("Failed to archive fact %d: %s", fact_id, e)
        return count

    def _is_contradiction(self, new_text: str, existing_text: str) -> bool:
        """Use classifier model to determine if two texts contradict."""
        try:
            if self._llm is None:
                from merkaba.llm import LLMClient
                self._llm = LLMClient()

            prompt = (
                f"Do these two statements contradict each other?\n\n"
                f"Statement A (new): {new_text}\n"
                f"Statement B (existing): {existing_text}\n\n"
                f"Reply with exactly YES or NO."
            )
            from merkaba.llm import RequestPriority
            from merkaba.config.defaults import DEFAULT_MODELS
            response = self._llm.chat_with_retry(
                message=prompt,
                system_prompt="You detect contradictions. Reply YES or NO only.",
                model_override=DEFAULT_MODELS["classifier"],
                priority=RequestPriority.BACKGROUND,
            )
            answer = (response.content or "").strip().upper()
            return answer.startswith("YES")
        except Exception as e:
            logger.warning("Contradiction LLM check failed: %s", e)
            return False

    @staticmethod
    def _item_text(item: dict[str, Any]) -> str:
        """Extract searchable text from a recall result item."""
        item_type = item.get("type", "")
        if item_type == "fact":
            return f"{item.get('category', '')} {item.get('key', '')} {item.get('value', '')}"
        elif item_type == "decision":
            return f"{item.get('decision', '')} {item.get('reasoning', '')}"
        elif item_type == "learning":
            return item.get("insight", "")
        elif item_type == "episode":
            return f"{item.get('task_type', '')} {item.get('summary', '')}"
        return str(item)

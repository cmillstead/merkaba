# src/merkaba/memory/lifecycle.py
import json
import logging
from dataclasses import dataclass, field
from merkaba.memory.store import MemoryStore
from merkaba.security.sanitizer import sanitize_memory_value

logger = logging.getLogger(__name__)


@dataclass
class MemoryDecayJob:
    """Decays relevance scores for stale memories and archives low-score items."""

    store: MemoryStore
    decay_factor: float = 0.95
    stale_days: int = 7
    archive_threshold: float = 0.1

    episode_max_age_days: int = 365

    def run(self) -> dict:
        """Run decay pass across all memory tables.

        Returns dict with {"decayed": N, "archived": N, "episodes_deleted": N}.
        """
        stats = self.store.decay_stale(
            decay_factor=self.decay_factor,
            stale_days=self.stale_days,
            archive_threshold=self.archive_threshold,
        )
        stats["episodes_deleted"] = self.store.delete_old_episodes(
            max_age_days=self.episode_max_age_days,
        )
        logger.info("Decay job complete: %s", stats)
        return stats


@dataclass
class SessionExtractor:
    """Extracts storable facts from chat session transcripts using a small LLM."""

    llm: object  # LLMClient
    store: MemoryStore
    model: str = "qwen3:4b"

    def extract(self, messages: list[dict], business_id: int = 0) -> list[dict]:
        """Extract facts from conversation messages.

        Args:
            messages: List of {"role": ..., "content": ...} dicts.
            business_id: Business to associate extracted facts with.

        Returns:
            List of stored fact dicts.
        """
        transcript = self._format_transcript(messages)
        if not transcript.strip():
            return []

        prompt = (
            "Extract key facts and entity relationships from this conversation. "
            "Return a JSON object with two arrays:\n"
            '  "facts": [{category, key, value, confidence (0-100)}]\n'
            '  "relationships": [{entity, entity_type, relation, related_entity, related_type}]\n'
            "Only include concrete, factual information worth remembering long-term. "
            'Return {"facts": [], "relationships": []} if nothing worth extracting.\n\n'
            f"Conversation:\n{transcript}"
        )

        try:
            response = self.llm.chat(
                message=prompt,
                system_prompt="You extract structured facts from conversations. Return only valid JSON.",
                model_override=self.model,
            )
            content = getattr(response, "content", None) or ""
            parsed = self._parse_response(content)
        except Exception as e:
            logger.warning("Session extraction LLM call failed: %s", e)
            return []

        # Handle both dict (new format) and list (backward compat)
        if isinstance(parsed, dict):
            items = parsed.get("facts", [])
            rels_list = parsed.get("relationships", [])
        else:
            items = parsed
            rels_list = []

        # Store relationships
        for rel in rels_list:
            entity = rel.get("entity", "")
            entity_type = rel.get("entity_type", "")
            relation = rel.get("relation", "")
            related_entity = rel.get("related_entity", "")
            related_type = rel.get("related_type", "")
            if not entity or not relation or not related_entity:
                continue
            if self._is_duplicate_relationship(business_id, entity, relation, related_entity):
                continue
            self.store.add_relationship(
                business_id=business_id,
                entity_type=entity_type or related_type,
                entity_id=entity,
                relation=relation,
                related_entity=related_entity,
            )

        stored = []
        for item in items:
            category = item.get("category", "general")
            key = sanitize_memory_value(item.get("key", ""))
            value = sanitize_memory_value(item.get("value", ""))
            confidence = item.get("confidence", 70)

            if not key or not value:
                continue

            # Deduplicate against existing facts
            if self._is_duplicate(business_id, category, key, value):
                continue

            fact_id = self.store.add_fact(
                business_id=business_id,
                category=category,
                key=key,
                value=value,
                confidence=confidence,
                source="session_extraction",
            )
            stored.append({"id": fact_id, "category": category, "key": key, "value": value})

        logger.info("Session extraction: %d facts stored from %d messages", len(stored), len(messages))
        return stored

    def _format_transcript(self, messages: list[dict]) -> str:
        lines = []
        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if content:
                lines.append(f"{role}: {content}")
        return "\n".join(lines)

    def _parse_response(self, content: str) -> list[dict] | dict:
        """Parse LLM response as JSON array or object, tolerating markdown fences."""
        text = content.strip()
        # Strip markdown code fences
        if text.startswith("```"):
            lines = text.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines)
        try:
            result = json.loads(text)
            if isinstance(result, (list, dict)):
                return result
        except (json.JSONDecodeError, ValueError):
            logger.debug("Failed to parse extraction response: %s", text[:200])
        return []

    def _is_duplicate(self, business_id: int, category: str, key: str, value: str) -> bool:
        """Check if a similar fact already exists via keyword overlap."""
        existing = self.store.get_facts(business_id, category=category)
        for fact in existing:
            if fact["key"] == key:
                return True
            # Fuzzy: if value words overlap significantly
            existing_words = set(fact["value"].lower().split())
            new_words = set(value.lower().split())
            if existing_words and new_words:
                overlap = len(existing_words & new_words) / max(len(existing_words), len(new_words))
                if overlap > 0.7:
                    return True
        return False

    def _is_duplicate_relationship(
        self, business_id: int, entity: str, relation: str, related_entity: str
    ) -> bool:
        """Check if an identical relationship already exists (case-insensitive)."""
        existing = self.store.get_relationships(business_id)
        for rel in existing:
            if (
                rel["entity_id"].lower() == entity.lower()
                and rel["relation"].lower() == relation.lower()
                and rel["related_entity"].lower() == related_entity.lower()
            ):
                return True
        return False


@dataclass
class MemoryConsolidationJob:
    """Groups related facts and summarizes them using an LLM."""

    store: MemoryStore
    llm: object  # LLMClient
    model: str = "qwen3:4b"
    min_group_size: int = 5
    vectors: object | None = None

    def run(self) -> dict:
        """Run consolidation across all businesses.

        Returns dict with {"groups": N, "archived": N, "summaries": N}.
        """
        total_groups = 0
        total_archived = 0
        total_summaries = 0

        businesses = self.store.list_businesses()
        # Include business_id=0 for global facts
        business_ids = [0] + [b["id"] for b in businesses]

        for bid in business_ids:
            facts = self.store.get_facts(bid)
            groups = self._group_by_category(facts)

            for category, group_facts in groups.items():
                if len(group_facts) < self.min_group_size:
                    continue

                total_groups += 1
                summary = self._summarize_group(category, group_facts)
                if not summary:
                    continue

                # Store the summary as a new fact
                self.store.add_fact(
                    business_id=bid,
                    category=category,
                    key=f"{category}_summary",
                    value=summary,
                    confidence=80,
                    source="consolidation",
                )
                total_summaries += 1

                # Archive the originals
                for fact in group_facts:
                    self.store.archive("facts", fact["id"])
                    total_archived += 1

        if self.vectors is not None:
            try:
                self.vectors.rebuild_from_store(self.store)
                logger.info("Vector rebuild triggered after consolidation")
            except Exception as e:
                logger.warning("Post-consolidation vector rebuild failed: %s", e)

        stats = {"groups": total_groups, "archived": total_archived, "summaries": total_summaries}
        logger.info("Consolidation complete: %s", stats)
        return stats

    def _group_by_category(self, facts: list[dict]) -> dict[str, list[dict]]:
        groups: dict[str, list[dict]] = {}
        for fact in facts:
            cat = fact.get("category", "general")
            groups.setdefault(cat, []).append(fact)
        return groups

    def _summarize_group(self, category: str, facts: list[dict]) -> str | None:
        """Use LLM to produce a concise summary of a group of related facts."""
        fact_lines = "\n".join(f"- {f['key']}: {f['value']}" for f in facts)
        prompt = (
            f"Summarize these {len(facts)} related facts about '{category}' "
            f"into a single concise paragraph:\n\n{fact_lines}"
        )

        try:
            response = self.llm.chat(
                message=prompt,
                system_prompt="You produce concise factual summaries. Be brief.",
                model_override=self.model,
            )
            return response.content.strip()
        except Exception as e:
            logger.warning("Consolidation LLM call failed for %s: %s", category, e)
            return None

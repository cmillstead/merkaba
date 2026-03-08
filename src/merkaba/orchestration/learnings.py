# src/merkaba/orchestration/learnings.py
import json
import logging
from dataclasses import dataclass, field
from typing import Any

from merkaba.memory.store import MemoryStore
from merkaba.orchestration.workers import WorkerResult
from merkaba.config.defaults import DEFAULT_MODELS

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = """You are Merkaba's learning extractor. Analyze these recent task results and extract generalizable insights.

Recent completed tasks:
{task_summaries}

Existing learnings:
{existing_learnings}

Extract 0-3 new insights that:
1. Are generalizable across businesses (not business-specific)
2. Are not already known (check existing learnings)
3. Have concrete evidence from the task results

Respond in JSON: {{"learnings": [{{"category": "...", "insight": "...", "evidence": "...", "confidence": 50}}]}}
If no new insights, respond: {{"learnings": []}}

Response:"""


@dataclass
class LearningExtractor:
    """Extracts cross-business learnings from task execution results."""

    memory_store: MemoryStore
    model: str = None

    def __post_init__(self):
        if self.model is None:
            self.model = DEFAULT_MODELS["classifier"]
    batch_threshold: int = 10
    _completed_count: int = field(default=0, init=False)
    _recent_results: list[dict[str, Any]] = field(default_factory=list, init=False)

    def process(self, task: dict, result: WorkerResult) -> list[dict]:
        new_learnings = []

        # Always do rule-based extraction
        new_learnings.extend(self._extract_rule_based(task, result))

        # Accumulate for batch LLM extraction
        self._recent_results.append({
            "task_name": task["name"],
            "task_type": task["task_type"],
            "business_id": task.get("business_id"),
            "success": result.success,
            "output_summary": str(result.output)[:500],
        })
        self._completed_count += 1

        # Periodically do LLM extraction
        if self._completed_count >= self.batch_threshold:
            new_learnings.extend(self._extract_llm_based())
            self._completed_count = 0
            self._recent_results.clear()

        # Store new learnings
        for learning in new_learnings:
            self.memory_store.add_learning(
                category=learning["category"],
                insight=learning["insight"],
                evidence=learning.get("evidence"),
                confidence=learning.get("confidence", 50),
                source_business_id=task.get("business_id"),
            )

        return new_learnings

    def _extract_rule_based(self, task: dict, result: WorkerResult) -> list[dict]:
        learnings = []
        if not result.success and result.error:
            existing = self.memory_store.get_learnings(category="failure_pattern")
            error_type = result.error.split(":")[0] if ":" in result.error else result.error[:50]
            already_known = any(error_type in l["insight"] for l in existing)
            if not already_known:
                learnings.append({
                    "category": "failure_pattern",
                    "insight": f"Task type '{task['task_type']}' can fail with: {error_type}",
                    "evidence": f"task_id={task['id']}, error={result.error[:200]}",
                    "confidence": 40,
                })
        return learnings

    def _extract_llm_based(self) -> list[dict]:
        if not self._recent_results:
            return []

        existing = self.memory_store.get_learnings()
        existing_summary = "\n".join(
            f"- [{l['category']}] {l['insight']}" for l in existing[:20]
        ) or "None yet"

        task_summary = "\n".join(
            f"- {r['task_name']} ({r['task_type']}): "
            f"{'success' if r['success'] else 'failed'} - {r['output_summary'][:200]}"
            for r in self._recent_results
        )

        prompt = EXTRACTION_PROMPT.format(
            task_summaries=task_summary,
            existing_learnings=existing_summary,
        )

        try:
            import ollama
            response = ollama.chat(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = response["message"]["content"]
            try:
                data = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                logger.warning("LLM returned non-JSON learning output: %s", raw[:200])
                return []
            return data.get("learnings", [])
        except Exception as e:
            logger.error("Learning extraction LLM call failed: %s", e)
            return []

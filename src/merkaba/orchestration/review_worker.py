# src/merkaba/orchestration/review_worker.py
"""ReviewWorker: reviews code output against criteria using LLM."""

import logging
from dataclasses import dataclass

from merkaba.orchestration.workers import Worker, WorkerResult, register_worker

logger = logging.getLogger(__name__)

REVIEW_SYSTEM_PROMPT = """You are a code reviewer. Given code and review criteria, provide a thorough review.

Structure your review as:
1. **Summary** — brief overall assessment
2. **Issues** — specific problems found (if any)
3. **Suggestions** — improvements to consider

Be concise and actionable. If the code is good, say so briefly."""


@dataclass
class ReviewWorker(Worker):
    """Reviews code output against criteria."""

    def execute(self, task: dict) -> WorkerResult:
        payload = task.get("payload") or {}
        output_text = payload.get("output_text", "")
        criteria = payload.get("review_criteria", "Check for correctness, best practices, and potential issues.")
        task_spec = payload.get("task_spec", "")

        if not output_text:
            return WorkerResult(
                success=False,
                output={},
                error="No code provided for review",
            )

        prompt_parts = []
        if task_spec:
            prompt_parts.append(f"## Original Spec\n{task_spec}")
        prompt_parts.append(f"## Code to Review\n{output_text}")
        prompt_parts.append(f"## Review Criteria\n{criteria}")
        prompt_parts.append("Provide your review.")

        prompt = "\n\n".join(prompt_parts)

        try:
            response = self._ask_llm(prompt, system_prompt=REVIEW_SYSTEM_PROMPT)
        except Exception as e:
            logger.error("Review LLM call failed: %s", e)
            return WorkerResult(
                success=False,
                output={},
                error=f"LLM review failed: {e}",
            )

        return WorkerResult(
            success=True,
            output={"review": response},
        )


register_worker("review", ReviewWorker)

# src/merkaba/orchestration/heartbeat.py
import logging
from dataclasses import dataclass
from typing import Any

from merkaba.orchestration.queue import TaskQueue
from merkaba.config.defaults import DEFAULT_MODELS

logger = logging.getLogger(__name__)

TRIAGE_PROMPT = """You are Merkaba's heartbeat monitor. Analyze the current state and decide what to do.

Recent task runs:
{recent_runs}

Task stats:
{stats}

Failed tasks:
{failed_tasks}

Respond with exactly one of:
- IDLE (nothing needs attention)
- INVESTIGATE <topic> (something looks off, needs investigation)
- ACT <action> (take a specific action)

Response:"""


@dataclass
class Heartbeat:
    """Light model triage — runs periodically to check if Merkaba needs to act."""

    queue: TaskQueue
    model: str = None

    def __post_init__(self):
        if self.model is None:
            self.model = DEFAULT_MODELS["classifier"]

    def check(self) -> str:
        """Run heartbeat triage. Returns: IDLE | INVESTIGATE <topic> | ACT <action>"""
        context = self._gather_context()
        prompt = TRIAGE_PROMPT.format(**context)

        try:
            import ollama

            response = ollama.chat(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = response["message"]["content"].strip()
            return self._parse_response(raw)
        except Exception as e:
            logger.error("Heartbeat model call failed: %s", e)
            return "IDLE"

    def _gather_context(self) -> dict[str, str]:
        stats = self.queue.stats()
        failed = self.queue.list_tasks(status="failed")
        failed_summary = "\n".join(
            f"- {t['name']} (id={t['id']}, type={t['task_type']})" for t in failed
        ) or "None"

        # Get recent runs across all tasks
        recent_runs = self._get_recent_runs(limit=10)
        runs_summary = "\n".join(
            f"- task_id={r['task_id']} status={r['status']} at={r['started_at']}"
            for r in recent_runs
        ) or "None"

        stats_summary = ", ".join(f"{k}={v}" for k, v in stats.items())

        return {
            "recent_runs": runs_summary,
            "stats": stats_summary,
            "failed_tasks": failed_summary,
        }

    def _get_recent_runs(self, limit: int = 10) -> list[dict[str, Any]]:
        return self.queue.get_recent_runs(limit=limit)

    def _parse_response(self, raw: str) -> str:
        # Extract the first line that starts with IDLE, INVESTIGATE, or ACT
        for line in raw.splitlines():
            line = line.strip()
            if line.startswith("IDLE"):
                return "IDLE"
            if line.startswith("INVESTIGATE"):
                return line
            if line.startswith("ACT"):
                return line
        logger.warning("Unparseable heartbeat response: %s", raw)
        return "IDLE"

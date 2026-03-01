# src/friday/orchestration/scheduler.py
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from friday.orchestration.queue import TaskQueue

logger = logging.getLogger(__name__)


@dataclass
class Scheduler:
    """Task scheduler daemon. Finds due tasks and dispatches them."""

    queue: TaskQueue
    on_task_due: Callable[[dict], dict] | None = None

    def tick(self) -> list[dict[str, Any]]:
        """One scheduler cycle: find due tasks, execute them, log results.

        Note: there is a minor race between start_run() changing the task
        status and compute_next_run() reading the task back.  This is
        acceptable for a single-process scheduler; a multi-process design
        would need row-level locking or an atomic compare-and-swap.
        """
        due = self.queue.get_due_tasks()
        for task in due:
            run_id = self.queue.start_run(task["id"])
            try:
                result = self._dispatch(task)
                self.queue.finish_run(run_id, "success", result=result)
            except Exception as e:
                logger.error("Task %s failed: %s", task["id"], e)
                self.queue.finish_run(run_id, "failed", error=str(e))
            self.queue.compute_next_run(task["id"])
        return due

    def run_loop(self, interval: int = 60) -> None:
        """Run tick() in a loop every `interval` seconds."""
        logger.info("Scheduler starting (interval=%ds)", interval)
        try:
            while True:
                try:
                    due = self.tick()
                    if due:
                        logger.info("Processed %d due tasks", len(due))
                except Exception as e:
                    logger.error("Scheduler tick error: %s", e)
                time.sleep(interval)
        except KeyboardInterrupt:
            logger.info("Scheduler stopped")

    def _dispatch(self, task: dict) -> dict:
        """Call on_task_due callback, or default stub."""
        if self.on_task_due:
            return self.on_task_due(task)
        logger.info("Stub dispatch for task %s (%s)", task["id"], task["name"])
        return {"status": "stub", "message": f"Task {task['name']} dispatched (no handler)"}

# src/merkaba/orchestration/memory_workers.py
import logging
from dataclasses import dataclass
from typing import Any

from merkaba.memory.store import MemoryStore
from merkaba.memory.lifecycle import MemoryDecayJob
from merkaba.orchestration.workers import Worker, WorkerResult, register_worker

logger = logging.getLogger(__name__)


@dataclass
class MemoryDecayWorker(Worker):
    """Worker that runs memory decay as a scheduled task."""

    memory_store: MemoryStore | None = None

    def execute(self, task: dict) -> WorkerResult:
        store = self.memory_store
        if store is None:
            store = MemoryStore()
        try:
            job = MemoryDecayJob(store=store)
            stats = job.run()
            store.emit("items_decayed", {"count": stats.get("archived", 0), "stats": stats})
            return WorkerResult(success=True, output=stats)
        except Exception as e:
            logger.error("Memory decay failed: %s", e)
            return WorkerResult(success=False, output={}, error=str(e))
        finally:
            if self.memory_store is None and store:
                store.close()


@dataclass
class MemoryConsolidationWorker(Worker):
    """Worker that runs memory consolidation as a scheduled task."""

    memory_store: MemoryStore | None = None
    llm: Any = None

    def execute(self, task: dict) -> WorkerResult:
        from merkaba.memory.lifecycle import MemoryConsolidationJob

        store = self.memory_store
        if store is None:
            store = MemoryStore()
        try:
            llm = self.llm
            if llm is None:
                from merkaba.llm import LLMClient
                llm = LLMClient()
            job = MemoryConsolidationJob(store=store, llm=llm)
            stats = job.run()
            store.emit("items_consolidated", {"count": stats.get("archived", 0), "stats": stats})
            return WorkerResult(success=True, output=stats)
        except Exception as e:
            logger.error("Memory consolidation failed: %s", e)
            return WorkerResult(success=False, output={}, error=str(e))
        finally:
            if self.memory_store is None and store:
                store.close()


def register_memory_jobs(queue) -> None:
    """Register memory lifecycle tasks in the scheduler queue. Idempotent."""
    existing = queue.list_tasks()
    existing_names = {t["name"] for t in existing}

    if "memory_decay" not in existing_names:
        queue.add_task(
            name="memory_decay",
            task_type="memory_decay",
            schedule="0 3 * * *",
            autonomy_level=1,
        )
        logger.info("Registered memory_decay scheduled task")

    if "memory_consolidate" not in existing_names:
        queue.add_task(
            name="memory_consolidate",
            task_type="memory_consolidate",
            schedule="0 4 * * 0",
            autonomy_level=1,
        )
        logger.info("Registered memory_consolidate scheduled task")


register_worker("memory_decay", MemoryDecayWorker)
register_worker("memory_consolidate", MemoryConsolidationWorker)

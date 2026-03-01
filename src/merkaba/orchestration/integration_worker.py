# src/merkaba/orchestration/integration_worker.py
"""Worker that bridges integration adapters into the orchestration pipeline."""

import logging
from dataclasses import dataclass

from merkaba.orchestration.workers import Worker, WorkerResult, register_worker
from merkaba.integrations.base import get_adapter_class

logger = logging.getLogger(__name__)


@dataclass
class IntegrationWorker(Worker):
    """Executes integration adapter actions as orchestration tasks.

    Expected task payload:
        {"adapter": "stripe", "action": "get_balance", "params": {}}
    """

    def execute(self, task: dict) -> WorkerResult:
        payload = task.get("payload") or {}
        adapter_name = payload.get("adapter")
        action = payload.get("action")

        if not adapter_name or not action:
            return WorkerResult(
                success=False, output={},
                error="Task payload must include 'adapter' and 'action'",
            )

        adapter_cls = get_adapter_class(adapter_name)
        if adapter_cls is None:
            return WorkerResult(success=False, output={}, error=f"Adapter not found: {adapter_name}")

        adapter = adapter_cls(name=adapter_name, business_id=self.business_id)

        if not adapter.connect():
            return WorkerResult(success=False, output={}, error=f"Failed to connect adapter: {adapter_name}")

        try:
            params = payload.get("params") or {}
            result = adapter.execute(action, params)
            return WorkerResult(
                success=True, output=result,
                facts_learned=[{
                    "category": "integration",
                    "key": f"{adapter_name}:{action}",
                    "value": str(result)[:500],
                }],
            )
        except Exception as e:
            logger.error("Integration worker error: %s", e)
            return WorkerResult(success=False, output={}, error=str(e))
        finally:
            adapter.disconnect()


register_worker("integration", IntegrationWorker)

# tests/test_integration_supervisor_flow.py
"""Integration tests for Supervisor -> Worker -> Memory pipeline."""

import sys
from dataclasses import dataclass
from unittest.mock import MagicMock

import pytest

# Mock ollama before any merkaba imports that touch LLMClient
sys.modules.setdefault("ollama", MagicMock())

from merkaba.memory.store import MemoryStore
from merkaba.orchestration.queue import TaskQueue
from merkaba.orchestration.workers import (
    Worker,
    WorkerResult,
    register_worker,
    WORKER_REGISTRY,
)
from merkaba.orchestration.supervisor import Supervisor


# --- Stub workers ---

@dataclass
class StubWorker(Worker):
    def execute(self, task):
        return WorkerResult(
            success=True,
            output={"result": "stub_ok"},
            facts_learned=[{"category": "test", "key": "k1", "value": "v1"}],
            decisions_made=[{"action_type": "test", "decision": "did it", "reasoning": "why not"}],
        )


@dataclass
class FailingWorker(Worker):
    def execute(self, task):
        raise RuntimeError("worker exploded")


@dataclass
class ApprovalWorker(Worker):
    def execute(self, task):
        return WorkerResult(
            success=True,
            output={"action": "send_email"},
            needs_approval=[{"action": "send_email", "to": "user@example.com"}],
        )


@pytest.fixture(autouse=True)
def register_test_workers():
    register_worker("_int_stub", StubWorker)
    register_worker("_int_failing", FailingWorker)
    register_worker("_int_approval", ApprovalWorker)
    yield
    for key in ("_int_stub", "_int_failing", "_int_approval"):
        WORKER_REGISTRY.pop(key, None)


@pytest.fixture
def supervisor(memory_store):
    sup = Supervisor(memory_store=memory_store)
    yield sup
    sup.close()


# --- Tests ---


class TestTaskDispatch:
    def test_dispatch_to_stub_worker(self, supervisor, memory_store):
        bid = memory_store.add_business(name="TestBiz", type="test")
        task = {"id": 1, "name": "Stub Task", "task_type": "_int_stub", "business_id": bid}
        result = supervisor.handle_task(task)
        assert result["success"] is True
        assert result["output"]["result"] == "stub_ok"

    def test_facts_written_to_memory_store(self, supervisor, memory_store):
        bid = memory_store.add_business(name="TestBiz", type="test")
        task = {"id": 2, "name": "Stub Task", "task_type": "_int_stub", "business_id": bid}
        supervisor.handle_task(task)
        facts = memory_store.get_facts(bid)
        assert len(facts) == 1
        assert facts[0]["key"] == "k1"
        assert facts[0]["value"] == "v1"

    def test_decisions_written_to_memory_store(self, supervisor, memory_store):
        bid = memory_store.add_business(name="TestBiz", type="test")
        task = {"id": 3, "name": "Stub Task", "task_type": "_int_stub", "business_id": bid}
        supervisor.handle_task(task)
        decisions = memory_store.get_decisions(bid)
        assert len(decisions) == 1
        assert decisions[0]["decision"] == "did it"


class TestApprovals:
    def test_approvals_dispatched_to_callback(self, supervisor, memory_store):
        approvals = []
        supervisor.on_needs_approval = lambda action: approvals.append(action)
        bid = memory_store.add_business(name="TestBiz", type="test")
        task = {"id": 4, "name": "Approval Task", "task_type": "_int_approval", "business_id": bid}
        supervisor.handle_task(task)
        assert len(approvals) == 1
        assert approvals[0]["action"] == "send_email"
        assert approvals[0]["task_id"] == 4

    def test_no_approval_callback_does_not_crash(self, supervisor, memory_store):
        supervisor.on_needs_approval = None
        bid = memory_store.add_business(name="TestBiz", type="test")
        task = {"id": 5, "name": "Approval Task", "task_type": "_int_approval", "business_id": bid}
        result = supervisor.handle_task(task)
        assert result["success"] is True


class TestFailures:
    def test_worker_exception_returns_failure(self, supervisor):
        task = {"id": 6, "name": "Fail Task", "task_type": "_int_failing", "business_id": None}
        result = supervisor.handle_task(task)
        assert result["success"] is False
        assert "worker exploded" in result["error"]

    def test_unknown_task_type_returns_failure(self, supervisor):
        task = {"id": 7, "name": "Unknown", "task_type": "nonexistent_xyz"}
        result = supervisor.handle_task(task)
        assert result["success"] is False
        assert "No worker" in result["error"]

    def test_no_business_id_skips_fact_storage(self, supervisor, memory_store):
        task = {"id": 8, "name": "Stub Task", "task_type": "_int_stub"}
        result = supervisor.handle_task(task)
        assert result["success"] is True


class TestFullPipeline:
    def test_task_to_memory(self, supervisor, memory_store, task_queue):
        """TaskQueue.start_run -> Supervisor.handle_task -> finish_run -> verify memory + status."""
        bid = memory_store.add_business(name="Pipeline Biz", type="test")
        task_id = task_queue.add_task(name="Pipeline Task", task_type="_int_stub", business_id=bid)
        run_id = task_queue.start_run(task_id)

        task = task_queue.get_task(task_id)
        result = supervisor.handle_task(task)

        task_queue.finish_run(run_id, status="completed", result=result)

        # Verify memory was written
        facts = memory_store.get_facts(bid)
        assert len(facts) >= 1

        # Verify task status reset to pending (for recurring tasks)
        updated = task_queue.get_task(task_id)
        assert updated["status"] == "pending"

    def test_failed_pipeline_records_failure(self, supervisor, memory_store, task_queue):
        """FailingWorker + finish_run('failed') -> verify task status."""
        bid = memory_store.add_business(name="Fail Biz", type="test")
        task_id = task_queue.add_task(name="Fail Task", task_type="_int_failing", business_id=bid)
        run_id = task_queue.start_run(task_id)

        task = task_queue.get_task(task_id)
        result = supervisor.handle_task(task)

        task_queue.finish_run(run_id, status="failed", error=result.get("error"))

        updated = task_queue.get_task(task_id)
        assert updated["status"] == "failed"

    def test_dead_letter_after_repeated_failures(self, task_queue):
        """Fail MAX_TASK_FAILURES times -> verify dead_letter status."""
        task_id = task_queue.add_task(name="DLQ Task", task_type="_int_failing")

        for _ in range(TaskQueue.MAX_TASK_FAILURES):
            run_id = task_queue.start_run(task_id)
            task_queue.finish_run(run_id, status="failed", error="boom")

        updated = task_queue.get_task(task_id)
        assert updated["status"] == "dead_letter"

        dlq = task_queue.list_dead_letters()
        assert len(dlq) >= 1
        assert dlq[0]["task_id"] == task_id

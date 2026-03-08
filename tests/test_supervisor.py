# tests/test_supervisor.py
import tempfile
import os
from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import pytest

from merkaba.memory.store import MemoryStore
from merkaba.orchestration.workers import Worker, WorkerResult, register_worker, WORKER_REGISTRY
from merkaba.orchestration.supervisor import Supervisor


@pytest.fixture
def memory():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "memory.db")
        store = MemoryStore(db_path=db_path)
        yield store
        store.close()


@pytest.fixture
def supervisor(memory):
    sup = Supervisor(memory_store=memory)
    yield sup
    sup.close()


# --- StubWorker for testing ---


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
def register_stub_workers():
    register_worker("_stub", StubWorker)
    register_worker("_failing", FailingWorker)
    register_worker("_approval", ApprovalWorker)
    yield
    for key in ("_stub", "_failing", "_approval"):
        WORKER_REGISTRY.pop(key, None)


# --- Tests ---


def test_handle_task_success(supervisor, memory):
    bid = memory.add_business(name="TestBiz", type="test")
    task = {"id": 1, "name": "Stub Task", "task_type": "_stub", "business_id": bid}
    result = supervisor.handle_task(task)

    assert result["success"] is True
    assert result["output"]["result"] == "stub_ok"
    assert result["error"] is None


def test_handle_task_stores_facts(supervisor, memory):
    bid = memory.add_business(name="TestBiz", type="test")
    task = {"id": 2, "name": "Stub Task", "task_type": "_stub", "business_id": bid}
    supervisor.handle_task(task)

    facts = memory.get_facts(bid)
    assert len(facts) == 1
    assert facts[0]["key"] == "k1"


def test_handle_task_stores_decisions(supervisor, memory):
    bid = memory.add_business(name="TestBiz", type="test")
    task = {"id": 3, "name": "Stub Task", "task_type": "_stub", "business_id": bid}
    supervisor.handle_task(task)

    decisions = memory.get_decisions(bid)
    assert len(decisions) == 1
    assert decisions[0]["decision"] == "did it"


def test_handle_task_no_business_id_skips_storage(supervisor, memory):
    task = {"id": 4, "name": "Stub Task", "task_type": "_stub"}
    result = supervisor.handle_task(task)

    assert result["success"] is True
    # No business_id — nothing stored (no crash either)


def test_handle_task_unknown_worker(supervisor):
    task = {"id": 5, "name": "Unknown", "task_type": "nonexistent_xyz"}
    result = supervisor.handle_task(task)

    assert result["success"] is False
    assert "No worker" in result["error"]


def test_handle_task_worker_exception(supervisor):
    task = {"id": 6, "name": "Fail Task", "task_type": "_failing", "business_id": None}
    result = supervisor.handle_task(task)

    assert result["success"] is False
    assert "worker exploded" in result["error"]


def test_handle_task_approval_callback(supervisor, memory):
    approvals = []
    supervisor.on_needs_approval = lambda action: approvals.append(action)

    bid = memory.add_business(name="TestBiz", type="test")
    task = {"id": 7, "name": "Approval Task", "task_type": "_approval", "business_id": bid}
    supervisor.handle_task(task)

    assert len(approvals) == 1
    assert approvals[0]["action"] == "send_email"
    assert approvals[0]["task_id"] == 7


def test_handle_task_approval_no_callback(supervisor, memory):
    """When no on_needs_approval handler is set, approvals are logged but don't crash."""
    supervisor.on_needs_approval = None
    bid = memory.add_business(name="TestBiz", type="test")
    task = {"id": 8, "name": "Approval Task", "task_type": "_approval", "business_id": bid}
    result = supervisor.handle_task(task)

    assert result["success"] is True


def test_build_tool_registry_default(supervisor):
    """Default autonomy_level=1 should register read-only tools (no crash on missing)."""
    task = {"id": 9, "name": "Test", "task_type": "_stub", "autonomy_level": 1}
    # Just verify it doesn't crash
    registry = supervisor._build_tool_registry(task)
    assert registry is not None


def test_close_idempotent(memory):
    sup = Supervisor(memory_store=memory)
    sup.close()
    sup.close()  # second close should not crash


# --- Dispatch mode tests ---

from merkaba.orchestration.supervisor import DispatchMode


def test_select_dispatch_mode_direct_default(supervisor):
    """Regular task type returns DIRECT by default."""
    task = {"id": 100, "task_type": "research", "payload": {}}
    assert supervisor.select_dispatch_mode(task) == DispatchMode.DIRECT


def test_select_dispatch_mode_simple_task_type(supervisor):
    """health_check (in SIMPLE_TASK_TYPES) returns DIRECT."""
    task = {"id": 101, "task_type": "health_check", "payload": {}}
    assert supervisor.select_dispatch_mode(task) == DispatchMode.DIRECT


def test_select_dispatch_mode_competitive_via_override(supervisor):
    """Explicit dispatch_mode override returns COMPETITIVE."""
    task = {"id": 102, "task_type": "general", "payload": {"dispatch_mode": "competitive"}}
    assert supervisor.select_dispatch_mode(task) == DispatchMode.COMPETITIVE


def test_select_dispatch_mode_explore_then_execute(supervisor):
    """Task with explore_paths in payload returns EXPLORE_THEN_EXECUTE."""
    task = {"id": 103, "task_type": "research", "payload": {"explore_paths": ["/some/dir"]}}
    assert supervisor.select_dispatch_mode(task) == DispatchMode.EXPLORE_THEN_EXECUTE


def test_select_dispatch_mode_explicit_override(supervisor):
    """Explicit payload.dispatch_mode overrides heuristics."""
    task = {"id": 104, "task_type": "research", "payload": {"dispatch_mode": "competitive"}}
    assert supervisor.select_dispatch_mode(task) == DispatchMode.COMPETITIVE


def test_select_dispatch_mode_invalid_override_falls_back(supervisor):
    """Unknown dispatch_mode value falls back to DIRECT."""
    task = {"id": 105, "task_type": "research", "payload": {"dispatch_mode": "bogus_mode"}}
    assert supervisor.select_dispatch_mode(task) == DispatchMode.DIRECT


# --- verify_integration tests ---


def test_verify_integration_failed_result(supervisor, memory):
    """When result.success is False, verify_integration returns DISCONNECTED immediately."""
    bid = memory.add_business(name="TestBiz", type="test")
    task = {
        "id": 200,
        "name": "Integration Test",
        "task_type": "_stub",
        "business_id": bid,
        "payload": {"integration_targets": ["target_a"]},
    }
    failed_result = WorkerResult(success=False, output={}, error="worker failed")
    status = supervisor.verify_integration(task, failed_result)
    assert status == "DISCONNECTED"


# --- dispatch_competition tests ---


def test_dispatch_competition_returns_variants(supervisor, memory):
    """dispatch_competition returns a list of WorkerResult with variant emphases injected."""
    bid = memory.add_business(name="TestBiz", type="test")
    task = {"id": 300, "name": "Content Task", "task_type": "_stub", "business_id": bid, "payload": {}}
    results = supervisor.dispatch_competition(task, n_competitors=2)

    assert len(results) == 2
    assert all(isinstance(r, WorkerResult) for r in results)
    assert all(r.success for r in results)


# --- select_winner tests ---


def test_select_winner_no_successful_results(supervisor):
    """When all results failed, returns the first result."""
    task = {"id": 400, "name": "Winner Test", "task_type": "_stub"}
    r1 = WorkerResult(success=False, output={}, error="fail1")
    r2 = WorkerResult(success=False, output={}, error="fail2")
    winner = supervisor.select_winner(task, [r1, r2])
    assert winner is r1
    assert winner.error == "fail1"


def test_select_winner_one_successful(supervisor):
    """When exactly one result succeeded, returns it without LLM judge."""
    task = {"id": 401, "name": "Winner Test", "task_type": "_stub"}
    r_fail = WorkerResult(success=False, output={}, error="nope")
    r_ok = WorkerResult(success=True, output={"data": "good"})
    winner = supervisor.select_winner(task, [r_fail, r_ok])
    assert winner is r_ok
    assert winner.success is True


# --- _record_episode tests ---


def test_record_episode_no_business_id(supervisor):
    """_record_episode skips without error when task has no business_id."""
    task = {"id": 500, "name": "Episode Test", "task_type": "_stub"}
    result = WorkerResult(success=True, output={"data": "ok"})
    # Should not raise, should not call LLM
    supervisor._record_episode(task, result)


# --- _handle_explore_then_execute tests ---


def test_handle_explore_then_execute_injects_context(supervisor, memory):
    """_handle_explore_then_execute calls ExplorationOrchestrator and injects context."""
    bid = memory.add_business(name="TestBiz", type="test")
    task = {
        "id": 600,
        "name": "Explore Task",
        "task_type": "_stub",
        "business_id": bid,
        "payload": {"explore_paths": ["/fake/path"]},
    }

    from merkaba.orchestration.explorer import ExplorationResult

    mock_result = ExplorationResult(summaries=["Found important context here"], token_estimate=10)

    with patch("merkaba.orchestration.explorer.ExplorationOrchestrator") as MockOrch:
        mock_instance = MagicMock()
        mock_instance.explore.return_value = mock_result
        MockOrch.return_value = mock_instance

        worker_result = supervisor._handle_explore_then_execute(task, StubWorker)

    # ExplorationOrchestrator.explore was called with the task and paths
    mock_instance.explore.assert_called_once_with(task, ["/fake/path"])
    # Worker still executed successfully (StubWorker returns success)
    assert worker_result.success is True
    assert worker_result.output["result"] == "stub_ok"


# --- Protocol-based mock test ---


def test_supervisor_accepts_memory_backend_protocol():
    """Supervisor should accept any object satisfying the MemoryBackend protocol."""
    from merkaba.protocols import MemoryBackend

    # Use a plain MagicMock that auto-creates attributes (close, add_episode, etc.)
    # but verify it still satisfies the protocol via structural typing.
    mock_store = MagicMock()
    mock_store.add_fact = MagicMock(return_value=1)
    mock_store.get_facts = MagicMock(return_value=[])
    mock_store.add_decision = MagicMock(return_value=1)
    mock_store.get_decisions = MagicMock(return_value=[])

    assert isinstance(mock_store, MemoryBackend)

    sup = Supervisor(memory_store=mock_store)

    task = {"id": 700, "name": "Protocol Test", "task_type": "_stub", "business_id": 1}
    result = sup.handle_task(task)

    assert result["success"] is True
    mock_store.add_fact.assert_called_once()
    mock_store.add_decision.assert_called_once()
    sup.close()


# --- Integration check caching tests ---


def test_verify_integration_cache_avoids_second_llm_call(supervisor, memory):
    """Two identical verify_integration calls should only invoke LLM once."""
    bid = memory.add_business(name="TestBiz", type="test")
    task = {
        "id": 800,
        "name": "Cache Test",
        "task_type": "_stub",
        "business_id": bid,
        "payload": {"integration_targets": ["target_a", "target_b"]},
    }
    ok_result = WorkerResult(success=True, output={"data": "ok"})

    mock_response = MagicMock()
    mock_response.content = "CONNECTED"

    with patch("merkaba.llm.LLMClient", autospec=True) as MockLLM:
        mock_instance = MagicMock()
        mock_instance.chat_with_fallback.return_value = mock_response
        MockLLM.return_value = mock_instance

        status1 = supervisor.verify_integration(task, ok_result)
        status2 = supervisor.verify_integration(task, ok_result)

    assert status1 == "CONNECTED"
    assert status2 == "CONNECTED"
    # LLM should have been called exactly once — second call served from cache
    mock_instance.chat_with_fallback.assert_called_once()


def test_verify_integration_cache_key_includes_sorted_targets(supervisor, memory):
    """Cache key uses sorted targets, so different orderings hit the same cache entry."""
    bid = memory.add_business(name="TestBiz", type="test")
    task_ab = {
        "id": 801,
        "name": "Order Test",
        "task_type": "_stub",
        "business_id": bid,
        "payload": {"integration_targets": ["alpha", "beta"]},
    }
    task_ba = {
        "id": 802,
        "name": "Order Test",
        "task_type": "_stub",
        "business_id": bid,
        "payload": {"integration_targets": ["beta", "alpha"]},
    }
    ok_result = WorkerResult(success=True, output={"data": "ok"})

    mock_response = MagicMock()
    mock_response.content = "PARTIAL"

    with patch("merkaba.llm.LLMClient", autospec=True) as MockLLM:
        mock_instance = MagicMock()
        mock_instance.chat_with_fallback.return_value = mock_response
        MockLLM.return_value = mock_instance

        status1 = supervisor.verify_integration(task_ab, ok_result)
        status2 = supervisor.verify_integration(task_ba, ok_result)

    assert status1 == "PARTIAL"
    assert status2 == "PARTIAL"
    mock_instance.chat_with_fallback.assert_called_once()


def test_verify_integration_cache_expires_after_ttl(supervisor, memory):
    """Cache entries older than 30 minutes should be evicted, triggering a new LLM call."""
    from datetime import datetime, timedelta, timezone

    bid = memory.add_business(name="TestBiz", type="test")
    task = {
        "id": 803,
        "name": "TTL Test",
        "task_type": "_stub",
        "business_id": bid,
        "payload": {"integration_targets": ["target_x"]},
    }
    ok_result = WorkerResult(success=True, output={"data": "ok"})

    mock_response = MagicMock()
    mock_response.content = "CONNECTED"

    with patch("merkaba.llm.LLMClient", autospec=True) as MockLLM:
        mock_instance = MagicMock()
        mock_instance.chat_with_fallback.return_value = mock_response
        MockLLM.return_value = mock_instance

        # First call — populates cache
        status1 = supervisor.verify_integration(task, ok_result)

        # Manually expire the cache entry
        cache_key = "_stub:target_x"
        old_time = datetime.now(timezone.utc) - timedelta(minutes=31)
        supervisor._integration_cache[cache_key] = ("CONNECTED", old_time)

        # Second call — cache expired, should call LLM again
        status2 = supervisor.verify_integration(task, ok_result)

    assert status1 == "CONNECTED"
    assert status2 == "CONNECTED"
    assert mock_instance.chat_with_fallback.call_count == 2


def test_verify_integration_different_task_types_use_separate_cache(supervisor, memory):
    """Different task_types should produce different cache keys."""
    bid = memory.add_business(name="TestBiz", type="test")
    task_a = {
        "id": 804,
        "name": "Type A",
        "task_type": "_stub",
        "business_id": bid,
        "payload": {"integration_targets": ["target_z"]},
    }
    task_b = {
        "id": 805,
        "name": "Type B",
        "task_type": "_approval",
        "business_id": bid,
        "payload": {"integration_targets": ["target_z"]},
    }
    ok_result = WorkerResult(success=True, output={"data": "ok"})

    mock_response = MagicMock()
    mock_response.content = "CONNECTED"

    with patch("merkaba.llm.LLMClient", autospec=True) as MockLLM:
        mock_instance = MagicMock()
        mock_instance.chat_with_fallback.return_value = mock_response
        MockLLM.return_value = mock_instance

        supervisor.verify_integration(task_a, ok_result)
        supervisor.verify_integration(task_b, ok_result)

    # Different task_types = different cache keys = 2 LLM calls
    assert mock_instance.chat_with_fallback.call_count == 2

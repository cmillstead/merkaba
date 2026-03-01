# tests/test_workers.py
import json
import sys
from dataclasses import dataclass
from unittest.mock import MagicMock

import pytest

from merkaba.orchestration.workers import (
    Worker,
    WorkerResult,
    WORKER_REGISTRY,
    register_worker,
    get_worker_class,
    HealthCheckWorker,
    ResearchWorker,
)


# --- WorkerResult ---


def test_worker_result_defaults():
    r = WorkerResult(success=True, output={"key": "val"})
    assert r.success is True
    assert r.error is None
    assert r.decisions_made == []
    assert r.facts_learned == []
    assert r.needs_approval == []


def test_worker_result_with_extras():
    r = WorkerResult(
        success=False,
        output={},
        error="boom",
        facts_learned=[{"category": "x", "key": "k", "value": "v"}],
    )
    assert r.error == "boom"
    assert len(r.facts_learned) == 1


# --- Registry ---


def test_builtin_workers_registered():
    assert "health_check" in WORKER_REGISTRY
    assert "research" in WORKER_REGISTRY


def test_get_worker_class_found():
    assert get_worker_class("health_check") is HealthCheckWorker


def test_get_worker_class_missing():
    assert get_worker_class("nonexistent_type_xyz") is None


def test_register_custom_worker():
    @dataclass
    class Dummy(Worker):
        def execute(self, task):
            return WorkerResult(success=True, output={})

    register_worker("_test_dummy", Dummy)
    assert get_worker_class("_test_dummy") is Dummy
    # cleanup
    del WORKER_REGISTRY["_test_dummy"]


# --- Worker base ---


def test_base_execute_raises():
    w = Worker()
    with pytest.raises(NotImplementedError):
        w.execute({})


def test_build_context_basic():
    w = Worker()
    ctx = w._build_context({"name": "Test Task", "task_type": "check"})
    assert "Test Task" in ctx
    assert "check" in ctx


def test_build_context_with_payload():
    w = Worker()
    ctx = w._build_context({"name": "T", "task_type": "t", "payload": {"q": "hello"}})
    assert "hello" in ctx


# --- StubWorker for LLM tests ---


@dataclass
class StubWorker(Worker):
    """Worker that returns canned LLM responses for testing."""

    canned_response: str = '{"status": "healthy"}'

    def execute(self, task):
        return WorkerResult(success=True, output=json.loads(self.canned_response))


# --- HealthCheckWorker (mocked LLM) ---


@pytest.fixture
def mock_llm_client():
    mock = MagicMock()
    return mock


def test_health_check_worker_valid_json(mock_llm_client):
    worker = HealthCheckWorker()
    mock_llm_client.chat_with_fallback.return_value = MagicMock(
        content='{"status": "healthy", "issues": [], "recommendations": ["keep going"]}'
    )
    worker._llm = mock_llm_client

    task = {"id": 1, "name": "Health", "task_type": "health_check"}
    result = worker.execute(task)

    assert result.success is True
    assert result.output["status"] == "healthy"


def test_health_check_worker_invalid_json(mock_llm_client):
    worker = HealthCheckWorker()
    mock_llm_client.chat_with_fallback.return_value = MagicMock(content="Not JSON at all")
    worker._llm = mock_llm_client

    task = {"id": 2, "name": "Health", "task_type": "health_check"}
    result = worker.execute(task)

    assert result.success is True
    assert result.output["status"] == "unknown"
    assert "raw_response" in result.output


# --- ResearchWorker (mocked LLM) ---


def test_research_worker_valid_json(mock_llm_client):
    worker = ResearchWorker()
    mock_llm_client.chat_with_fallback.return_value = MagicMock(
        content='{"findings": ["f1"], "recommendations": ["r1"]}',
        tool_calls=None,
    )
    worker._llm = mock_llm_client

    task = {"id": 3, "name": "Research", "task_type": "research", "payload": {"query": "test query"}}
    result = worker.execute(task)

    assert result.success is True
    assert "findings" in result.output
    assert len(result.facts_learned) == 1
    assert result.facts_learned[0]["category"] == "research"


def test_research_worker_invalid_json(mock_llm_client):
    worker = ResearchWorker()
    mock_llm_client.chat_with_fallback.return_value = MagicMock(
        content="free text response",
        tool_calls=None,
    )
    worker._llm = mock_llm_client

    task = {"id": 4, "name": "Research", "task_type": "research"}
    result = worker.execute(task)

    assert result.success is True
    assert "raw_response" in result.output

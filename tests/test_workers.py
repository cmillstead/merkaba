# tests/test_workers.py
import json
import sys
from dataclasses import dataclass
from unittest.mock import MagicMock, patch

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
from merkaba.security import PermissionManager, PermissionDenied
from merkaba.tools.base import PermissionTier, Tool, ToolResult


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


# --- PermissionManager integration ---


def test_worker_has_permission_manager_attribute():
    """Worker dataclass must expose a permission_manager field."""
    w = Worker()
    assert hasattr(w, "permission_manager")
    assert isinstance(w.permission_manager, PermissionManager)


def test_worker_permission_manager_default_is_safe_level():
    """Default PermissionManager must auto-approve only SAFE tools."""
    w = Worker()
    assert w.permission_manager.auto_approve_level == PermissionTier.SAFE


def test_worker_permission_manager_is_independent_per_instance():
    """Each Worker instance must get its own PermissionManager (not shared)."""
    w1 = Worker()
    w2 = Worker()
    assert w1.permission_manager is not w2.permission_manager


def _make_tool(name: str, tier: PermissionTier, return_value: str = "ok") -> Tool:
    """Build a minimal Tool for testing."""
    return Tool(
        name=name,
        description=f"Test tool {name}",
        function=lambda **kwargs: return_value,
        permission_tier=tier,
        parameters={},
    )


def _make_tool_registry(*tools: Tool):
    """Return a minimal ToolRegistry-like object backed by the given tools."""
    registry = MagicMock()
    tool_map = {t.name: t for t in tools}
    registry.list_tools.return_value = list(tool_map.values())
    registry.get.side_effect = lambda name: tool_map.get(name)
    registry.to_ollama_format.return_value = [t.to_ollama_format() for t in tools]
    return registry


def _tool_call(name: str, arguments: dict | None = None):
    tc = MagicMock()
    tc.name = name
    tc.arguments = arguments or {}
    return tc


def test_worker_allows_safe_tool(mock_llm_client):
    """SAFE tool must execute without raising PermissionDenied."""
    safe_tool = _make_tool("safe_tool", PermissionTier.SAFE, "safe result")
    registry = _make_tool_registry(safe_tool)

    mock_llm_client.chat_with_fallback.side_effect = [
        MagicMock(tool_calls=[_tool_call("safe_tool")]),
        MagicMock(tool_calls=None, content='{"ok": true}'),
    ]

    worker = ResearchWorker(tools=registry)
    worker._llm = mock_llm_client

    task = {"id": 10, "name": "Research", "task_type": "research"}
    result = worker.execute(task)

    # Tool was actually called (permission was granted)
    assert result.success is True
    # The safe tool's output should appear in subsequent LLM prompt — verifiable via call count
    assert mock_llm_client.chat_with_fallback.call_count >= 2


def test_worker_blocks_sensitive_tool_when_auto_approve_level_is_safe(mock_llm_client):
    """SENSITIVE tool must be blocked when auto_approve_level=SAFE (default)."""
    sensitive_tool = _make_tool("bash", PermissionTier.SENSITIVE)
    registry = _make_tool_registry(sensitive_tool)

    # LLM calls the sensitive tool once, then returns a final response
    mock_llm_client.chat_with_fallback.side_effect = [
        MagicMock(tool_calls=[_tool_call("bash", {"cmd": "rm -rf /"})]),
        MagicMock(tool_calls=None, content='{"findings": []}'),
    ]

    worker = ResearchWorker(tools=registry)
    worker._llm = mock_llm_client
    # Default auto_approve_level is SAFE — SENSITIVE must be denied

    task = {"id": 11, "name": "Research", "task_type": "research"}
    result = worker.execute(task)

    assert result.success is True
    # The tool function itself must never have been invoked
    # Verify by checking that the second LLM call received a "Permission denied" in the prompt
    second_call_args = mock_llm_client.chat_with_fallback.call_args_list[1]
    prompt_arg = second_call_args[1].get("message") or second_call_args[0][0]
    assert "Permission denied" in prompt_arg


def test_worker_blocks_destructive_tool(mock_llm_client):
    """DESTRUCTIVE tool must be blocked under default (SAFE) permission level."""
    destructive_tool = _make_tool("delete_data", PermissionTier.DESTRUCTIVE)
    registry = _make_tool_registry(destructive_tool)

    mock_llm_client.chat_with_fallback.side_effect = [
        MagicMock(tool_calls=[_tool_call("delete_data")]),
        MagicMock(tool_calls=None, content="done"),
    ]

    worker = ResearchWorker(tools=registry)
    worker._llm = mock_llm_client

    task = {"id": 12, "name": "Research", "task_type": "research"}
    result = worker.execute(task)

    assert result.success is True
    second_call_args = mock_llm_client.chat_with_fallback.call_args_list[1]
    prompt_arg = second_call_args[1].get("message") or second_call_args[0][0]
    assert "Permission denied" in prompt_arg


def test_worker_allows_sensitive_tool_when_permission_level_elevated(mock_llm_client):
    """SENSITIVE tool must be allowed when auto_approve_level=SENSITIVE."""
    sensitive_tool = _make_tool("bash", PermissionTier.SENSITIVE, "output text")
    registry = _make_tool_registry(sensitive_tool)

    mock_llm_client.chat_with_fallback.side_effect = [
        MagicMock(tool_calls=[_tool_call("bash", {"cmd": "ls"})]),
        MagicMock(tool_calls=None, content='{"findings": ["output text"]}'),
    ]

    pm = PermissionManager(auto_approve_level=PermissionTier.SENSITIVE)
    worker = ResearchWorker(tools=registry, permission_manager=pm)
    worker._llm = mock_llm_client

    task = {"id": 13, "name": "Research", "task_type": "research"}
    result = worker.execute(task)

    assert result.success is True
    second_call_args = mock_llm_client.chat_with_fallback.call_args_list[1]
    prompt_arg = second_call_args[1].get("message") or second_call_args[0][0]
    # Must NOT contain Permission denied — tool ran successfully
    assert "Permission denied" not in prompt_arg
    assert "output text" in prompt_arg


def test_worker_permission_denied_does_not_execute_tool_function(mock_llm_client):
    """Verify the tool function is never called when permission is denied."""
    called = []

    def dangerous_fn(**kwargs):
        called.append(True)
        return "boom"

    dangerous_tool = Tool(
        name="danger",
        description="Dangerous",
        function=dangerous_fn,
        permission_tier=PermissionTier.SENSITIVE,
        parameters={},
    )
    registry = _make_tool_registry(dangerous_tool)

    mock_llm_client.chat_with_fallback.side_effect = [
        MagicMock(tool_calls=[_tool_call("danger")]),
        MagicMock(tool_calls=None, content="done"),
    ]

    worker = ResearchWorker(tools=registry)
    worker._llm = mock_llm_client

    task = {"id": 14, "name": "Research", "task_type": "research"}
    worker.execute(task)

    assert called == [], "Tool function must not be invoked when permission is denied"


def test_worker_permission_denied_continues_to_next_tool_call(mock_llm_client):
    """After a PermissionDenied, the worker must continue (not crash) and return a result."""
    sensitive_tool = _make_tool("bash", PermissionTier.SENSITIVE)
    safe_tool = _make_tool("echo", PermissionTier.SAFE, "hello")
    registry = _make_tool_registry(sensitive_tool, safe_tool)

    mock_llm_client.chat_with_fallback.side_effect = [
        MagicMock(tool_calls=[_tool_call("bash"), _tool_call("echo")]),
        MagicMock(tool_calls=None, content='{"findings": []}'),
    ]

    worker = ResearchWorker(tools=registry)
    worker._llm = mock_llm_client

    task = {"id": 15, "name": "Research", "task_type": "research"}
    result = worker.execute(task)

    assert result.success is True
    # Both results were appended — denied for bash, success for echo
    second_call_args = mock_llm_client.chat_with_fallback.call_args_list[1]
    prompt_arg = second_call_args[1].get("message") or second_call_args[0][0]
    assert "Permission denied" in prompt_arg
    assert "hello" in prompt_arg

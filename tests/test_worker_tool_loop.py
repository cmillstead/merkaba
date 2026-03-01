# tests/test_worker_tool_loop.py
"""Tests for Worker._ask_llm_with_tools() multi-turn agentic loop."""

from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import pytest

from merkaba.llm import LLMResponse, ToolCall
from merkaba.orchestration.workers import Worker, WorkerResult
from merkaba.tools.base import Tool, ToolResult, PermissionTier
from merkaba.tools.registry import ToolRegistry


# --- Concrete test subclass (Worker.execute is abstract) ---


@dataclass
class StubWorker(Worker):
    """Minimal concrete worker for testing _ask_llm_with_tools."""

    def execute(self, task: dict) -> WorkerResult:
        return WorkerResult(success=True, output={})


# --- Helpers ---


def _make_tool(name: str, fn=None) -> Tool:
    """Create a simple Tool for registry injection."""
    if fn is None:
        fn = lambda **kwargs: f"result from {name}"
    return Tool(
        name=name,
        description=f"Test tool {name}",
        function=fn,
        permission_tier=PermissionTier.SAFE,
        parameters={"type": "object", "properties": {}},
    )


def _make_registry(*tools: Tool) -> ToolRegistry:
    """Build a ToolRegistry with the given tools."""
    registry = ToolRegistry()
    for t in tools:
        registry.register(t)
    return registry


# --- Tests ---


class TestNoToolCalls:
    """LLM returns content immediately with no tool_calls."""

    def test_returns_content_directly(self, mock_ollama, make_llm_response):
        worker = StubWorker(tools=_make_registry(_make_tool("dummy")))
        response = make_llm_response(content="Direct answer", tool_calls=None)

        with patch.object(worker, "_get_llm") as mock_get_llm:
            llm = MagicMock()
            llm.chat_with_fallback.return_value = response
            mock_get_llm.return_value = llm

            result = worker._ask_llm_with_tools("What is 2+2?")

        assert result == "Direct answer"
        llm.chat_with_fallback.assert_called_once()

    def test_returns_empty_string_when_content_is_none(self, mock_ollama, make_llm_response):
        worker = StubWorker(tools=_make_registry(_make_tool("dummy")))
        response = make_llm_response(content=None, tool_calls=None)

        with patch.object(worker, "_get_llm") as mock_get_llm:
            llm = MagicMock()
            llm.chat_with_fallback.return_value = response
            mock_get_llm.return_value = llm

            result = worker._ask_llm_with_tools("What is 2+2?")

        assert result == ""


class TestSingleToolCall:
    """LLM returns one tool call, then final content."""

    def test_tool_executed_and_content_returned(self, mock_ollama, make_llm_response):
        captured_args = {}

        def my_tool_fn(**kwargs):
            captured_args.update(kwargs)
            return "42"

        tool = _make_tool("calculator", fn=my_tool_fn)
        registry = _make_registry(tool)
        worker = StubWorker(tools=registry)

        response_with_tools = make_llm_response(
            content=None,
            tool_calls=[ToolCall(name="calculator", arguments={"x": 1})],
        )
        response_final = make_llm_response(content="The answer is 42")

        with patch.object(worker, "_get_llm") as mock_get_llm:
            llm = MagicMock()
            llm.chat_with_fallback.side_effect = [response_with_tools, response_final]
            mock_get_llm.return_value = llm

            result = worker._ask_llm_with_tools("Compute something")

        assert result == "The answer is 42"
        assert captured_args == {"x": 1}
        assert llm.chat_with_fallback.call_count == 2

    def test_tool_output_appended_to_formatted_prompt(self, mock_ollama, make_llm_response):
        tool = _make_tool("lookup", fn=lambda **kw: "found data")
        registry = _make_registry(tool)
        worker = StubWorker(tools=registry)

        response_with_tools = make_llm_response(
            content=None,
            tool_calls=[ToolCall(name="lookup", arguments={})],
        )
        response_final = make_llm_response(content="Done")

        with patch.object(worker, "_get_llm") as mock_get_llm:
            llm = MagicMock()
            llm.chat_with_fallback.side_effect = [response_with_tools, response_final]
            mock_get_llm.return_value = llm

            worker._ask_llm_with_tools("Find stuff")

        # Second call should contain the tool output in the message
        second_call_kwargs = llm.chat_with_fallback.call_args_list[1]
        message_arg = second_call_kwargs.kwargs.get("message", second_call_kwargs[1].get("message") if len(second_call_kwargs) > 1 else None)
        # Access via keyword args
        actual_message = llm.chat_with_fallback.call_args_list[1].kwargs["message"]
        assert "[lookup] found data" in actual_message
        assert "Tool results:" in actual_message
        assert "Continue with the task." in actual_message


class TestMultiTurnToolLoop:
    """LLM returns tool calls for multiple iterations before final content."""

    def test_two_iterations_then_final(self, mock_ollama, make_llm_response):
        call_count = {"tool_a": 0, "tool_b": 0}

        def tool_a_fn(**kw):
            call_count["tool_a"] += 1
            return "a_result"

        def tool_b_fn(**kw):
            call_count["tool_b"] += 1
            return "b_result"

        registry = _make_registry(
            _make_tool("tool_a", fn=tool_a_fn),
            _make_tool("tool_b", fn=tool_b_fn),
        )
        worker = StubWorker(tools=registry)

        iter1_response = make_llm_response(
            content=None,
            tool_calls=[ToolCall(name="tool_a", arguments={"q": "first"})],
        )
        iter2_response = make_llm_response(
            content=None,
            tool_calls=[ToolCall(name="tool_b", arguments={"q": "second"})],
        )
        final_response = make_llm_response(content="All done")

        with patch.object(worker, "_get_llm") as mock_get_llm:
            llm = MagicMock()
            llm.chat_with_fallback.side_effect = [iter1_response, iter2_response, final_response]
            mock_get_llm.return_value = llm

            result = worker._ask_llm_with_tools("Multi-step task")

        assert result == "All done"
        assert call_count["tool_a"] == 1
        assert call_count["tool_b"] == 1
        assert llm.chat_with_fallback.call_count == 3

    def test_multiple_tools_in_single_iteration(self, mock_ollama, make_llm_response):
        """LLM returns multiple tool_calls in a single response."""
        registry = _make_registry(
            _make_tool("fetch", fn=lambda **kw: "data_fetched"),
            _make_tool("parse", fn=lambda **kw: "data_parsed"),
        )
        worker = StubWorker(tools=registry)

        response_with_two_tools = make_llm_response(
            content=None,
            tool_calls=[
                ToolCall(name="fetch", arguments={}),
                ToolCall(name="parse", arguments={}),
            ],
        )
        final_response = make_llm_response(content="Combined result")

        with patch.object(worker, "_get_llm") as mock_get_llm:
            llm = MagicMock()
            llm.chat_with_fallback.side_effect = [response_with_two_tools, final_response]
            mock_get_llm.return_value = llm

            result = worker._ask_llm_with_tools("Do two things")

        assert result == "Combined result"

        # Check both tool outputs appear in the second call's message
        second_message = llm.chat_with_fallback.call_args_list[1].kwargs["message"]
        assert "[fetch] data_fetched" in second_message
        assert "[parse] data_parsed" in second_message


class TestToolNotFound:
    """LLM requests a tool that isn't registered."""

    def test_tool_not_found_message_in_prompt(self, mock_ollama, make_llm_response):
        registry = _make_registry(_make_tool("existing_tool"))
        worker = StubWorker(tools=registry)

        response_with_missing = make_llm_response(
            content=None,
            tool_calls=[ToolCall(name="nonexistent_tool", arguments={})],
        )
        final_response = make_llm_response(content="Recovered")

        with patch.object(worker, "_get_llm") as mock_get_llm:
            llm = MagicMock()
            llm.chat_with_fallback.side_effect = [response_with_missing, final_response]
            mock_get_llm.return_value = llm

            result = worker._ask_llm_with_tools("Use missing tool")

        assert result == "Recovered"
        second_message = llm.chat_with_fallback.call_args_list[1].kwargs["message"]
        assert "[nonexistent_tool] Tool not found" in second_message

    def test_tool_not_found_when_tools_is_none_but_llm_returns_tool_call(
        self, mock_ollama, make_llm_response
    ):
        """Edge case: self.tools is None, but LLM still returns tool_calls."""
        # With tools=None and no list_tools(), tools_fmt is None, but LLM might
        # still return tool_calls. The code handles this via `self.tools.get(tc.name) if self.tools else None`.
        worker = StubWorker(tools=None)

        response_with_tools = make_llm_response(
            content=None,
            tool_calls=[ToolCall(name="phantom", arguments={})],
        )
        final_response = make_llm_response(content="Handled")

        with patch.object(worker, "_get_llm") as mock_get_llm:
            llm = MagicMock()
            llm.chat_with_fallback.side_effect = [response_with_tools, final_response]
            mock_get_llm.return_value = llm

            result = worker._ask_llm_with_tools("Ghost tool")

        assert result == "Handled"
        second_message = llm.chat_with_fallback.call_args_list[1].kwargs["message"]
        assert "[phantom] Tool not found" in second_message


class TestMaxIterationsReached:
    """LLM always returns tool_calls, never final content."""

    def test_returns_empty_string_after_max_iterations(self, mock_ollama, make_llm_response):
        registry = _make_registry(_make_tool("infinite_tool"))
        worker = StubWorker(tools=registry, max_iterations=3)

        always_tool_calls = make_llm_response(
            content=None,
            tool_calls=[ToolCall(name="infinite_tool", arguments={})],
        )

        with patch.object(worker, "_get_llm") as mock_get_llm:
            llm = MagicMock()
            llm.chat_with_fallback.return_value = always_tool_calls
            mock_get_llm.return_value = llm

            result = worker._ask_llm_with_tools("Loop forever")

        assert result == ""
        assert llm.chat_with_fallback.call_count == 3

    def test_max_iterations_default_is_five(self, mock_ollama, make_llm_response):
        worker = StubWorker(tools=_make_registry(_make_tool("t")))
        assert worker.max_iterations == 5

        always_tool_calls = make_llm_response(
            content=None,
            tool_calls=[ToolCall(name="t", arguments={})],
        )

        with patch.object(worker, "_get_llm") as mock_get_llm:
            llm = MagicMock()
            llm.chat_with_fallback.return_value = always_tool_calls
            mock_get_llm.return_value = llm

            result = worker._ask_llm_with_tools("Loop forever default")

        assert result == ""
        assert llm.chat_with_fallback.call_count == 5

    def test_max_iterations_one(self, mock_ollama, make_llm_response):
        """With max_iterations=1, only one LLM call is made."""
        registry = _make_registry(_make_tool("t"))
        worker = StubWorker(tools=registry, max_iterations=1)

        always_tool_calls = make_llm_response(
            content=None,
            tool_calls=[ToolCall(name="t", arguments={})],
        )

        with patch.object(worker, "_get_llm") as mock_get_llm:
            llm = MagicMock()
            llm.chat_with_fallback.return_value = always_tool_calls
            mock_get_llm.return_value = llm

            result = worker._ask_llm_with_tools("Once only")

        assert result == ""
        assert llm.chat_with_fallback.call_count == 1


class TestToolExecutionError:
    """Tool's execute returns success=False with an error message."""

    def test_error_message_appended_instead_of_output(self, mock_ollama, make_llm_response):
        def failing_fn(**kwargs):
            raise ValueError("bad input")

        tool = _make_tool("bad_tool", fn=failing_fn)
        registry = _make_registry(tool)
        worker = StubWorker(tools=registry)

        response_with_tools = make_llm_response(
            content=None,
            tool_calls=[ToolCall(name="bad_tool", arguments={"x": 1})],
        )
        final_response = make_llm_response(content="Error handled")

        with patch.object(worker, "_get_llm") as mock_get_llm:
            llm = MagicMock()
            llm.chat_with_fallback.side_effect = [response_with_tools, final_response]
            mock_get_llm.return_value = llm

            result = worker._ask_llm_with_tools("Try bad tool")

        assert result == "Error handled"
        second_message = llm.chat_with_fallback.call_args_list[1].kwargs["message"]
        # The error branch: result.error (not result.output)
        assert "[bad_tool]" in second_message
        assert "ValueError" in second_message
        assert "bad input" in second_message

    def test_mixed_success_and_failure(self, mock_ollama, make_llm_response):
        """One tool succeeds, another fails, both results are appended."""
        registry = _make_registry(
            _make_tool("good_tool", fn=lambda **kw: "good_output"),
            _make_tool("bad_tool", fn=lambda **kw: (_ for _ in ()).throw(RuntimeError("oops"))),
        )
        worker = StubWorker(tools=registry)

        response_with_tools = make_llm_response(
            content=None,
            tool_calls=[
                ToolCall(name="good_tool", arguments={}),
                ToolCall(name="bad_tool", arguments={}),
            ],
        )
        final_response = make_llm_response(content="Mixed results")

        with patch.object(worker, "_get_llm") as mock_get_llm:
            llm = MagicMock()
            llm.chat_with_fallback.side_effect = [response_with_tools, final_response]
            mock_get_llm.return_value = llm

            result = worker._ask_llm_with_tools("Mixed tools")

        assert result == "Mixed results"
        second_message = llm.chat_with_fallback.call_args_list[1].kwargs["message"]
        assert "[good_tool] good_output" in second_message
        assert "[bad_tool]" in second_message
        assert "RuntimeError" in second_message


class TestNoToolsRegistered:
    """When self.tools is None, tools_fmt is None."""

    def test_tools_fmt_is_none_when_no_tools(self, mock_ollama, make_llm_response):
        worker = StubWorker(tools=None)
        response = make_llm_response(content="No tools needed")

        with patch.object(worker, "_get_llm") as mock_get_llm:
            llm = MagicMock()
            llm.chat_with_fallback.return_value = response
            mock_get_llm.return_value = llm

            result = worker._ask_llm_with_tools("Simple question")

        assert result == "No tools needed"
        call_kwargs = llm.chat_with_fallback.call_args.kwargs
        assert call_kwargs["tools"] is None

    def test_tools_fmt_is_none_when_registry_empty(self, mock_ollama, make_llm_response):
        """Registry exists but has no tools registered."""
        empty_registry = ToolRegistry()
        worker = StubWorker(tools=empty_registry)
        response = make_llm_response(content="Empty registry")

        with patch.object(worker, "_get_llm") as mock_get_llm:
            llm = MagicMock()
            llm.chat_with_fallback.return_value = response
            mock_get_llm.return_value = llm

            result = worker._ask_llm_with_tools("No tools available")

        assert result == "Empty registry"
        call_kwargs = llm.chat_with_fallback.call_args.kwargs
        assert call_kwargs["tools"] is None


class TestSystemPromptPassthrough:
    """Verify system_prompt is forwarded to LLM calls."""

    def test_system_prompt_passed_to_llm(self, mock_ollama, make_llm_response):
        registry = _make_registry(_make_tool("t"))
        worker = StubWorker(tools=registry)
        response = make_llm_response(content="OK")

        with patch.object(worker, "_get_llm") as mock_get_llm:
            llm = MagicMock()
            llm.chat_with_fallback.return_value = response
            mock_get_llm.return_value = llm

            worker._ask_llm_with_tools("Test", system_prompt="Be helpful")

        call_kwargs = llm.chat_with_fallback.call_args.kwargs
        assert call_kwargs["system_prompt"] == "Be helpful"

    def test_system_prompt_none_by_default(self, mock_ollama, make_llm_response):
        worker = StubWorker(tools=_make_registry(_make_tool("t")))
        response = make_llm_response(content="OK")

        with patch.object(worker, "_get_llm") as mock_get_llm:
            llm = MagicMock()
            llm.chat_with_fallback.return_value = response
            mock_get_llm.return_value = llm

            worker._ask_llm_with_tools("Test")

        call_kwargs = llm.chat_with_fallback.call_args.kwargs
        assert call_kwargs["system_prompt"] is None

    def test_system_prompt_persists_across_iterations(self, mock_ollama, make_llm_response):
        """System prompt should be passed on every iteration, not just the first."""
        registry = _make_registry(_make_tool("t"))
        worker = StubWorker(tools=registry)

        tool_response = make_llm_response(
            content=None,
            tool_calls=[ToolCall(name="t", arguments={})],
        )
        final_response = make_llm_response(content="Done")

        with patch.object(worker, "_get_llm") as mock_get_llm:
            llm = MagicMock()
            llm.chat_with_fallback.side_effect = [tool_response, final_response]
            mock_get_llm.return_value = llm

            worker._ask_llm_with_tools("Test", system_prompt="Stay focused")

        # Both calls should have the system_prompt
        for call in llm.chat_with_fallback.call_args_list:
            assert call.kwargs["system_prompt"] == "Stay focused"

# tests/e2e/test_e2e_chat.py
"""E2E tests for the agent chat flow via CLI.

All tests mock merkaba.agent.Agent to avoid requiring a real LLM backend.
The CLI command performs a lazy import (`from merkaba.agent import Agent`)
inside the `chat` function, so the patch target is "merkaba.agent.Agent".
"""

import pytest
from unittest.mock import patch, MagicMock

pytestmark = [pytest.mark.e2e]


def _patch_agent(run_return="Hello from Merkaba!", run_side_effect=None):
    """Return a context-manager that patches Agent and yields (MockAgent, mock_instance)."""
    patcher = patch("merkaba.agent.Agent")

    class _Ctx:
        def __enter__(self):
            MockAgent = patcher.start()
            mock_instance = MagicMock()
            if run_side_effect is not None:
                mock_instance.run.side_effect = run_side_effect
            else:
                mock_instance.run.return_value = run_return
            MockAgent.return_value = mock_instance
            return MockAgent, mock_instance

        def __exit__(self, *exc):
            patcher.stop()

    return _Ctx()


class TestChatSingleMessage:
    """Test: send a single message and verify Merkaba label appears."""

    def test_chat_single_message(self, cli_runner):
        runner, app = cli_runner
        with _patch_agent(run_return="Hello from Merkaba!") as (MockAgent, mock_instance):
            result = runner.invoke(app, ["chat", "Hi there"])
            assert result.exit_code == 0
            assert "Merkaba" in result.output
            mock_instance.run.assert_called_once_with("Hi there")


class TestChatWithModelFlag:
    """Test: --model flag is forwarded to Agent constructor."""

    def test_chat_with_model_flag(self, cli_runner):
        runner, app = cli_runner
        with _patch_agent(run_return="ok") as (MockAgent, mock_instance):
            result = runner.invoke(app, ["chat", "--model", "qwen3:8b", "hello"])
            assert result.exit_code == 0
            MockAgent.assert_called_once_with(model="qwen3:8b")


class TestChatAgentError:
    """Test: when Agent.run raises, the CLI shows an error message."""

    def test_chat_agent_error(self, cli_runner):
        runner, app = cli_runner
        with _patch_agent(run_side_effect=Exception("LLM connection refused")) as (
            MockAgent,
            mock_instance,
        ):
            result = runner.invoke(app, ["chat", "trigger error"])
            assert result.exit_code == 0
            assert "Error" in result.output
            assert "LLM connection refused" in result.output


class TestChatResponseContent:
    """Test: the actual response text from the agent appears in output."""

    def test_chat_response_content(self, cli_runner):
        runner, app = cli_runner
        expected = "The capital of France is Paris."
        with _patch_agent(run_return=expected) as (MockAgent, mock_instance):
            result = runner.invoke(app, ["chat", "What is the capital of France?"])
            assert result.exit_code == 0
            assert "Paris" in result.output
            assert "capital" in result.output.lower() or "Paris" in result.output


class TestChatToolCallFlow:
    """Test: agent returns text containing tool result information."""

    def test_chat_tool_call_flow(self, cli_runner):
        runner, app = cli_runner
        tool_response = (
            "I searched the files and found 3 matches.\n"
            "Tool result: grep returned results from src/main.py, src/utils.py, src/lib.py.\n"
            "Here is a summary of the findings."
        )
        with _patch_agent(run_return=tool_response) as (MockAgent, mock_instance):
            result = runner.invoke(app, ["chat", "Find all TODO comments"])
            assert result.exit_code == 0
            assert "3 matches" in result.output
            assert "summary" in result.output.lower()


class TestChatEmptyResponse:
    """Test: agent returning an empty string does not crash the CLI."""

    def test_chat_empty_response(self, cli_runner):
        runner, app = cli_runner
        with _patch_agent(run_return="") as (MockAgent, mock_instance):
            result = runner.invoke(app, ["chat", "say nothing"])
            assert result.exit_code == 0
            assert "Merkaba" in result.output


class TestChatMultilineResponse:
    """Test: agent returning multi-line markdown does not crash."""

    def test_chat_multiline_response(self, cli_runner):
        runner, app = cli_runner
        multiline = (
            "# Report\n\n"
            "Here are the results:\n\n"
            "- Item one\n"
            "- Item two\n"
            "- Item three\n\n"
            "```python\nprint('hello')\n```\n\n"
            "Done."
        )
        with _patch_agent(run_return=multiline) as (MockAgent, mock_instance):
            result = runner.invoke(app, ["chat", "generate a report"])
            assert result.exit_code == 0
            assert "Report" in result.output
            assert "Done" in result.output


class TestChatWithMemoryContext:
    """Test: with seeded memory, Agent is still created and called normally."""

    def test_chat_with_memory_context(self, cli_runner, seeded_memory):
        runner, app = cli_runner
        biz_id = seeded_memory["business_id"]
        assert biz_id is not None

        with _patch_agent(run_return="Memory context loaded.") as (MockAgent, mock_instance):
            result = runner.invoke(app, ["chat", "What do you know about the shop?"])
            assert result.exit_code == 0
            MockAgent.assert_called_once()
            mock_instance.run.assert_called_once_with("What do you know about the shop?")
            assert "Memory context loaded" in result.output

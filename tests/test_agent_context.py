# tests/test_agent_context.py
"""Tests for Agent context management — tool result trimming."""
import sys
from unittest.mock import MagicMock

if "ollama" not in sys.modules:
    mock_ollama = MagicMock()
    mock_ollama.ResponseError = type("ResponseError", (Exception,), {})
    sys.modules["ollama"] = mock_ollama

from merkaba.agent import Agent
from merkaba.memory.context_budget import ContextWindowConfig


def test_format_conversation_trims_long_tool_results(disable_llm_gate):
    """Long tool results get head/tail trimmed."""
    agent = Agent.__new__(Agent)
    agent._tree = MagicMock()
    agent.context_config = ContextWindowConfig(head_chars=1500, tail_chars=1500)

    long_content = "H" * 1500 + "M" * 5000 + "T" * 1500
    mock_msg = MagicMock()
    mock_msg.role = "tool"
    mock_msg.content = long_content
    mock_msg.metadata = {}

    agent._tree.get_active_branch.return_value = [mock_msg]

    result = agent._format_conversation()
    assert "[5000 chars trimmed]" in result
    assert result.startswith("Tool Result: " + "H" * 1500)
    assert result.endswith("T" * 1500)


def test_format_conversation_preserves_short_tool_results(disable_llm_gate):
    """Short tool results are preserved as-is."""
    agent = Agent.__new__(Agent)
    agent._tree = MagicMock()
    agent.context_config = ContextWindowConfig(head_chars=1500, tail_chars=1500)

    mock_msg = MagicMock()
    mock_msg.role = "tool"
    mock_msg.content = "short result"
    mock_msg.metadata = {}

    agent._tree.get_active_branch.return_value = [mock_msg]

    result = agent._format_conversation()
    assert result == "Tool Result: short result"


def test_format_conversation_handles_none_tool_content(disable_llm_gate):
    """Tool results with None content are handled gracefully."""
    agent = Agent.__new__(Agent)
    agent._tree = MagicMock()
    agent.context_config = ContextWindowConfig(head_chars=1500, tail_chars=1500)

    mock_msg = MagicMock()
    mock_msg.role = "tool"
    mock_msg.content = None
    mock_msg.metadata = {}

    agent._tree.get_active_branch.return_value = [mock_msg]

    result = agent._format_conversation()
    assert result == "Tool Result: "


def test_format_conversation_exact_threshold_not_trimmed(disable_llm_gate):
    """Content exactly at the threshold (head + tail + 100) is NOT trimmed."""
    agent = Agent.__new__(Agent)
    agent._tree = MagicMock()
    agent.context_config = ContextWindowConfig(head_chars=1500, tail_chars=1500)

    # Exactly at threshold: 1500 + 1500 + 100 = 3100 chars
    exact_content = "X" * 3100
    mock_msg = MagicMock()
    mock_msg.role = "tool"
    mock_msg.content = exact_content
    mock_msg.metadata = {}

    agent._tree.get_active_branch.return_value = [mock_msg]

    result = agent._format_conversation()
    assert "trimmed" not in result
    assert result == "Tool Result: " + exact_content


def test_format_conversation_just_over_threshold_trimmed(disable_llm_gate):
    """Content one char over threshold IS trimmed."""
    agent = Agent.__new__(Agent)
    agent._tree = MagicMock()
    agent.context_config = ContextWindowConfig(head_chars=1500, tail_chars=1500)

    # Just over threshold: 3101 chars
    over_content = "A" * 1500 + "B" * 101 + "C" * 1500
    mock_msg = MagicMock()
    mock_msg.role = "tool"
    mock_msg.content = over_content
    mock_msg.metadata = {}

    agent._tree.get_active_branch.return_value = [mock_msg]

    result = agent._format_conversation()
    assert "[101 chars trimmed]" in result
    assert result.startswith("Tool Result: " + "A" * 1500)
    assert result.endswith("C" * 1500)


def test_format_conversation_mixed_messages(disable_llm_gate):
    """Trimming works correctly in a conversation with mixed message types."""
    agent = Agent.__new__(Agent)
    agent._tree = MagicMock()
    agent.context_config = ContextWindowConfig(head_chars=100, tail_chars=100)

    user_msg = MagicMock()
    user_msg.role = "user"
    user_msg.content = "hello"
    user_msg.metadata = {}

    tool_msg = MagicMock()
    tool_msg.role = "tool"
    tool_msg.content = "S" * 100 + "X" * 500 + "E" * 100
    tool_msg.metadata = {}

    assistant_msg = MagicMock()
    assistant_msg.role = "assistant"
    assistant_msg.content = "done"
    assistant_msg.metadata = {}

    agent._tree.get_active_branch.return_value = [user_msg, tool_msg, assistant_msg]

    result = agent._format_conversation()
    assert result.startswith("User: hello\n\n")
    assert "[500 chars trimmed]" in result
    assert result.endswith("Assistant: done")
    assert "Tool Result: " + "S" * 100 in result
    assert "E" * 100 + "\n\nAssistant: done" in result

# tests/test_agent_context.py
"""Tests for Agent context management — tool result trimming and compression."""
import sys
from unittest.mock import MagicMock, patch

import pytest

if "ollama" not in sys.modules:
    mock_ollama = MagicMock()
    mock_ollama.ResponseError = type("ResponseError", (Exception,), {})
    sys.modules["ollama"] = mock_ollama

from merkaba.agent import Agent
from merkaba.llm import LLMResponse
from merkaba.memory.context_budget import ContextWindowConfig
from merkaba.memory.conversation import ConversationTree


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


# ---------- Compression integration ----------


@pytest.fixture
def agent_for_compression(tmp_path):
    """Create an Agent wired for compression testing."""
    with patch("merkaba.agent.SecurityScanner"), \
         patch("merkaba.agent.PluginRegistry"), \
         patch("merkaba.memory.vectors.VectorMemory", side_effect=ImportError):
        a = Agent(
            plugins_enabled=False,
            memory_storage_dir=str(tmp_path / "conversations"),
            prompt_dir=str(tmp_path / "merkaba_config"),
        )
        a.input_classifier = MagicMock()
        a.input_classifier.classify.return_value = (True, None, "complex")
        a._extract_session_memories = MagicMock()
        yield a


def test_agent_compresses_when_over_threshold(agent_for_compression):
    """Agent triggers compression when context exceeds threshold during run()."""
    agent = agent_for_compression
    # Set a very low threshold so compression fires easily
    agent.context_config.max_context_tokens = 100
    agent.context_config.compaction_threshold = 0.5

    # Fill conversation with enough content to trigger compression
    for i in range(20):
        agent._tree.append("user", f"Message {i} " + "x" * 100)
        agent._tree.append("assistant", f"Response {i} " + "y" * 100)

    # Mock LLM: first call returns summary (for compression), second returns final answer
    agent.llm.chat_with_fallback = MagicMock(
        return_value=LLMResponse(content="Summary of conversation.", model="test"),
    )

    result = agent.run("trigger compression")

    # Verify some messages were pruned (compression happened)
    pruned_count = sum(1 for m in agent._tree.messages.values() if m.pruned)
    assert pruned_count > 0, "Expected some messages to be pruned by compression"

    # Verify summary was inserted
    summary_msgs = [
        m for m in agent._tree.messages.values()
        if m.metadata.get("type") == "compression_summary"
    ]
    assert len(summary_msgs) == 1
    assert "[context optimized]" in summary_msgs[0].content


def test_agent_no_compression_below_threshold(agent_for_compression):
    """Agent does NOT compress when context is below threshold."""
    agent = agent_for_compression
    # Default high threshold — a few messages should not trigger it
    agent.context_config.max_context_tokens = 128000
    agent.context_config.compaction_threshold = 0.80

    agent._tree.append("user", "hello")
    agent._tree.append("assistant", "hi there")

    agent.llm.chat_with_fallback = MagicMock(
        return_value=LLMResponse(content="Final answer", model="test"),
    )

    result = agent.run("another question")
    assert result == "Final answer"

    # No pruning should have occurred
    pruned_count = sum(1 for m in agent._tree.messages.values() if m.pruned)
    assert pruned_count == 0

    # LLM called only once (for the main response, not for summary generation)
    assert agent.llm.chat_with_fallback.call_count == 1


def test_generate_compression_summary_calls_llm(disable_llm_gate):
    """_generate_compression_summary uses the simple tier to summarize."""
    agent = Agent.__new__(Agent)
    agent._tree = ConversationTree()
    agent._tree.append("user", "hello")
    agent._tree.append("assistant", "hi")
    agent.context_config = ContextWindowConfig()
    agent.llm = MagicMock()
    agent.llm.chat_with_fallback.return_value = LLMResponse(
        content="Conversation summary.", model="test"
    )

    summary = agent._generate_compression_summary()

    assert summary == "Conversation summary."
    call_kwargs = agent.llm.chat_with_fallback.call_args
    assert call_kwargs.kwargs.get("tier") == "simple"
    assert "summarizer" in call_kwargs.kwargs.get("system_prompt", "").lower()


def test_generate_compression_summary_fallback_on_error(disable_llm_gate):
    """When LLM fails, _generate_compression_summary returns fallback text."""
    agent = Agent.__new__(Agent)
    agent._tree = ConversationTree()
    agent._tree.append("user", "hello")
    agent.context_config = ContextWindowConfig()
    agent.llm = MagicMock()
    agent.llm.chat_with_fallback.side_effect = RuntimeError("LLM down")

    summary = agent._generate_compression_summary()

    assert "summary unavailable" in summary


def test_generate_compression_summary_fallback_on_none_content(disable_llm_gate):
    """When LLM returns None content, use fallback text."""
    agent = Agent.__new__(Agent)
    agent._tree = ConversationTree()
    agent._tree.append("user", "hello")
    agent.context_config = ContextWindowConfig()
    agent.llm = MagicMock()
    agent.llm.chat_with_fallback.return_value = LLMResponse(
        content=None, model="test"
    )

    summary = agent._generate_compression_summary()

    assert summary == "Previous conversation context."


def test_compression_preserves_recent_turns(agent_for_compression):
    """After compression, recent turns remain accessible in the active branch."""
    agent = agent_for_compression
    agent.context_config.max_context_tokens = 100
    agent.context_config.compaction_threshold = 0.5

    # Add many turns
    for i in range(25):
        agent._tree.append("user", f"Message {i} " + "x" * 100)
        agent._tree.append("assistant", f"Response {i} " + "y" * 100)

    agent.llm.chat_with_fallback = MagicMock(
        return_value=LLMResponse(content="done", model="test"),
    )

    agent.run("final question")

    # Active branch should contain the summary + recent turns + the latest exchange
    branch = agent._tree.get_active_branch()
    roles = [m.role for m in branch]

    # Summary system message should be in the branch
    system_msgs = [m for m in branch if m.role == "system"
                   and m.metadata.get("type") == "compression_summary"]
    assert len(system_msgs) == 1

    # The latest user message ("final question") should be in the branch
    user_contents = [m.content for m in branch if m.role == "user"]
    assert "final question" in user_contents

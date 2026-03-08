# tests/test_conversation_tree.py
"""Tests for ConversationTree and agent integration."""

import sys
from unittest.mock import MagicMock, patch

import pytest

# Mock ollama before importing Agent
sys.modules.setdefault("ollama", MagicMock())

from merkaba.memory.conversation import ConversationTree, Message
from merkaba.llm import LLMResponse, ToolCall
from merkaba.agent import Agent
from merkaba.verification.deterministic import VerificationResult, CheckResult
from merkaba.tools.base import ToolResult


# --- ConversationTree unit tests ---


class TestConversationTree:
    def test_append_creates_message(self):
        """append() returns a Message with UUID and sets current_leaf."""
        tree = ConversationTree()
        msg = tree.append("user", "Hello")
        assert isinstance(msg, Message)
        assert msg.role == "user"
        assert msg.content == "Hello"
        assert msg.parent_id is None  # first message has no parent
        assert tree.current_leaf_id == msg.id
        assert msg.id in tree.messages

    def test_get_active_branch_linear(self):
        """Three linear appends return all three in order."""
        tree = ConversationTree()
        m1 = tree.append("user", "A")
        m2 = tree.append("assistant", "B")
        m3 = tree.append("tool", "C")
        branch = tree.get_active_branch()
        assert len(branch) == 3
        assert [m.content for m in branch] == ["A", "B", "C"]
        assert branch[1].parent_id == m1.id
        assert branch[2].parent_id == m2.id

    def test_branch_from_creates_fork(self):
        """branch_from + append creates a new branch from an earlier point."""
        tree = ConversationTree()
        m_a = tree.append("user", "A")
        tree.append("assistant", "B")
        tree.append("tool", "C")

        tree.branch_from(m_a.id)
        m_d = tree.append("assistant", "D")

        branch = tree.get_active_branch()
        assert len(branch) == 2
        assert [m.content for m in branch] == ["A", "D"]
        assert m_d.parent_id == m_a.id

    def test_branch_from_invalid_id_raises(self):
        """branch_from with unknown message_id raises KeyError."""
        tree = ConversationTree()
        tree.append("user", "A")
        with pytest.raises(KeyError, match="not found"):
            tree.branch_from("nonexistent-id")

    def test_prune_branch(self):
        """Pruned descendants are excluded from get_active_branch."""
        tree = ConversationTree()
        m_a = tree.append("user", "A")
        m_b = tree.append("assistant", "B")
        m_c = tree.append("tool", "C")

        tree.prune_branch(m_a.id)
        assert tree.messages[m_b.id].pruned is True
        assert tree.messages[m_c.id].pruned is True
        # A itself is NOT pruned (only descendants)
        assert tree.messages[m_a.id].pruned is False

        # Active branch from C should skip pruned messages
        branch = tree.get_active_branch()
        assert len(branch) == 1
        assert branch[0].content == "A"

    def test_inject_summary(self):
        """inject_summary creates a system message after the branch point."""
        tree = ConversationTree()
        m_a = tree.append("user", "A")
        tree.append("assistant", "B")

        summary_msg = tree.inject_summary(m_a.id, "Lesson learned")
        assert summary_msg.role == "system"
        assert summary_msg.content == "Lesson learned"
        assert summary_msg.metadata == {"type": "branch_summary"}
        assert summary_msg.parent_id == m_a.id

        branch = tree.get_active_branch()
        assert len(branch) == 2
        assert branch[0].content == "A"
        assert branch[1].content == "Lesson learned"

    def test_get_descendants(self):
        """_get_descendants finds all children recursively."""
        tree = ConversationTree()
        m_root = tree.append("user", "root")
        m_child = tree.append("assistant", "child")
        m_grandchild = tree.append("tool", "grandchild")

        descendants = tree._get_descendants(m_root.id)
        assert set(descendants) == {m_child.id, m_grandchild.id}

        # Leaf has no descendants
        assert tree._get_descendants(m_grandchild.id) == []

    def test_serialization_roundtrip(self):
        """to_serializable -> from_serializable preserves tree structure."""
        tree = ConversationTree()
        m_a = tree.append("user", "A")
        m_b = tree.append("assistant", "B", {"tool_calls": [{"name": "test"}]})
        tree.append("tool", "C")
        tree.prune_branch(m_b.id)

        data = tree.to_serializable()
        restored = ConversationTree.from_serializable(data)

        assert restored.session_id == tree.session_id
        assert restored.current_leaf_id == tree.current_leaf_id
        assert len(restored.messages) == len(tree.messages)
        assert restored.messages[m_a.id].content == "A"
        assert restored.messages[m_b.id].metadata == {"tool_calls": [{"name": "test"}]}
        # C is a descendant of B — should still be pruned
        for mid, msg in restored.messages.items():
            orig = tree.messages[mid]
            assert msg.pruned == orig.pruned


# --- Agent integration tests ---


@pytest.fixture
def agent(tmp_path):
    """Create an Agent with side effects disabled."""
    with patch("merkaba.agent.SecurityScanner") as MockScanner:
        MockScanner.return_value.quick_scan.return_value = MagicMock(has_issues=False)
        a = Agent(plugins_enabled=False, memory_storage_dir=str(tmp_path))
    a.input_classifier.enabled = False
    return a


class TestAgentTreeIntegration:
    def test_attach_session_restores_persisted_tree(self, agent):
        """attach_session should restore a saved branching tree when available."""
        root = agent._tree.append("user", "A")
        agent._tree.append("assistant", "B")
        agent._tree.branch_from(root.id)
        agent._tree.append("assistant", "C")
        agent.memory.append("user", "A")
        agent.memory.append("assistant", "B")
        agent.memory.append("assistant", "C")
        agent.memory.save(tree=agent._tree)

        with patch("merkaba.agent.SecurityScanner") as MockScanner:
            MockScanner.return_value.quick_scan.return_value = MagicMock(has_issues=False)
            restored = Agent(
                plugins_enabled=False,
                memory_storage_dir=agent.memory.storage_dir,
            )
        restored.input_classifier.enabled = False
        restored.attach_session(agent.memory.session_id)

        branch = restored._tree.get_active_branch()
        assert [msg.content for msg in branch] == ["A", "C"]

    def test_agent_uses_tree(self, agent):
        """After run(), agent._tree has messages."""
        agent.llm.chat_with_retry = MagicMock(
            return_value=LLMResponse(content="Hi!", model="test")
        )
        agent.run("Hello")
        assert len(agent._tree.messages) >= 2  # user + assistant at minimum

    def test_agent_format_conversation_from_tree(self, agent):
        """_format_conversation uses tree messages."""
        agent._tree.append("user", "What is 2+2?")
        agent._tree.append("assistant", "It's 4.")
        formatted = agent._format_conversation()
        assert "User: What is 2+2?" in formatted
        assert "Assistant: It's 4." in formatted

    def test_agent_branch_on_repeated_failure(self, agent):
        """Two verification failures on the same file trigger branch + summary."""
        from merkaba.tools.base import PermissionTier
        agent.permission_manager.auto_approve_level = PermissionTier.MODERATE

        fail_result = VerificationResult(
            passed=False,
            checks=[CheckResult(name="ruff", passed=False, output="E001 error")],
            summary="[ruff] FAILED:\nE001 error",
        )
        agent._verifier.verify = MagicMock(return_value=fail_result)

        fw_tool = agent.registry.get("file_write")
        original_execute = fw_tool.execute
        try:
            fw_tool.execute = MagicMock(return_value=ToolResult(success=True, output="Wrote 5 bytes"))

            # 3 LLM calls: tool(fail) -> tool(fail again, triggers branch) -> final
            tool_resp = LLMResponse(
                content=None, model="test",
                tool_calls=[ToolCall(name="file_write", arguments={"path": "/tmp/bad.py", "content": "x="})],
            )
            final_resp = LLMResponse(content="Fixed.", model="test")
            agent.llm.chat_with_retry = MagicMock(side_effect=[tool_resp, tool_resp, final_resp])

            result = agent.run("Write some code")
            assert result == "Fixed."

            # Verify branching occurred: there should be a system message in the tree
            system_msgs = [m for m in agent._tree.messages.values() if m.role == "system"]
            assert len(system_msgs) >= 1
            assert "failed verification" in system_msgs[0].content.lower()
        finally:
            fw_tool.execute = original_execute

    def test_agent_single_failure_no_branch(self, agent):
        """One verification failure doesn't trigger branching."""
        from merkaba.tools.base import PermissionTier
        agent.permission_manager.auto_approve_level = PermissionTier.MODERATE

        fail_result = VerificationResult(
            passed=False,
            checks=[CheckResult(name="ruff", passed=False, output="E001")],
            summary="[ruff] FAILED:\nE001",
        )
        agent._verifier.verify = MagicMock(return_value=fail_result)

        fw_tool = agent.registry.get("file_write")
        original_execute = fw_tool.execute
        try:
            fw_tool.execute = MagicMock(return_value=ToolResult(success=True, output="Wrote 5 bytes"))

            tool_resp = LLMResponse(
                content=None, model="test",
                tool_calls=[ToolCall(name="file_write", arguments={"path": "/tmp/bad.py", "content": "x="})],
            )
            final_resp = LLMResponse(content="Done.", model="test")
            agent.llm.chat_with_retry = MagicMock(side_effect=[tool_resp, final_resp])

            agent.run("Write code")

            # No system messages — branch was NOT triggered
            system_msgs = [m for m in agent._tree.messages.values() if m.role == "system"]
            assert len(system_msgs) == 0
        finally:
            fw_tool.execute = original_execute

    def test_agent_system_message_in_format(self, agent):
        """System/branch_summary messages appear in formatted output."""
        agent._tree.append("user", "Hello")
        agent._tree.inject_summary(
            agent._tree.current_leaf_id,
            "Previous attempt failed.",
        )
        formatted = agent._format_conversation()
        assert "System: Previous attempt failed." in formatted

    def test_agent_tree_and_memory_both_populated(self, agent):
        """Both _tree and memory (ConversationLog) receive messages."""
        agent.llm.chat_with_retry = MagicMock(
            return_value=LLMResponse(content="Response.", model="test")
        )
        agent.run("Input message")

        # Tree has messages
        assert len(agent._tree.messages) >= 2

        # ConversationLog also has messages
        history = agent.memory.get_history()
        assert len(history) >= 2
        roles = [h["role"] for h in history]
        assert "user" in roles
        assert "assistant" in roles

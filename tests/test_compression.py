# tests/test_compression.py
"""Tests for graceful context compression."""

from merkaba.memory.conversation import ConversationTree
from merkaba.memory.compression import compress_context, should_compress
from merkaba.memory.context_budget import ContextWindowConfig


def _build_tree_with_turns(n_turns: int) -> ConversationTree:
    """Build a tree with n user/assistant turn pairs."""
    tree = ConversationTree()
    for i in range(n_turns):
        tree.append("user", f"Question {i} " + "x" * 200)
        tree.append("assistant", f"Answer {i} " + "y" * 200)
    return tree


class TestShouldCompress:
    def test_under_threshold_returns_false(self):
        config = ContextWindowConfig(max_context_tokens=128000, compaction_threshold=0.80)
        assert not should_compress("short text", config)

    def test_over_threshold_returns_true(self):
        config = ContextWindowConfig(max_context_tokens=100, compaction_threshold=0.80)
        long_text = "x" * 500  # ~125 tokens at 4 chars/token, over 80 of 100
        assert should_compress(long_text, config)

    def test_exactly_at_threshold_returns_false(self):
        """At exactly 80% utilization, we should NOT compress (only above)."""
        config = ContextWindowConfig(max_context_tokens=100, compaction_threshold=0.80)
        # 80 tokens = 320 chars
        text = "x" * 320
        assert not should_compress(text, config)

    def test_empty_text_returns_false(self):
        config = ContextWindowConfig(max_context_tokens=100, compaction_threshold=0.80)
        assert not should_compress("", config)


class TestCompressContext:
    def test_prunes_old_turns(self):
        tree = _build_tree_with_turns(20)
        branch_before = len(tree.get_active_branch())
        assert branch_before == 40  # 20 user + 20 assistant

        summary_text = "Summary of earlier conversation."
        compressed_tree = compress_context(tree, summary_text, keep_recent_turns=10)

        branch_after = compressed_tree.get_active_branch()
        # Should have: summary message + 20 recent messages (10 turns x 2)
        assert len(branch_after) == 21  # 1 summary + 20 kept
        assert any("[context optimized]" in (m.content or "") for m in branch_after)
        # Recent messages preserved
        assert any("Question 19" in (m.content or "") for m in branch_after)
        # Old messages pruned
        assert not any("Question 0" in (m.content or "") for m in branch_after)

    def test_preserves_recent_turns_when_under_limit(self):
        tree = _build_tree_with_turns(5)
        summary_text = "Summary."
        compressed = compress_context(tree, summary_text, keep_recent_turns=5)
        branch = compressed.get_active_branch()
        # All 5 turns kept, nothing to compress
        assert len(branch) == 10  # All preserved
        assert not any("[context optimized]" in (m.content or "") for m in branch)

    def test_empty_tree(self):
        tree = ConversationTree()
        result = compress_context(tree, "summary")
        assert result.get_active_branch() == []

    def test_summary_has_context_optimized_prefix(self):
        tree = _build_tree_with_turns(15)
        compressed = compress_context(tree, "Earlier topics discussed.", keep_recent_turns=5)
        branch = compressed.get_active_branch()
        summary_msgs = [m for m in branch if m.role == "system"]
        assert len(summary_msgs) == 1
        assert summary_msgs[0].content.startswith("[context optimized]")
        assert "Earlier topics discussed." in summary_msgs[0].content

    def test_summary_metadata_type(self):
        tree = _build_tree_with_turns(15)
        compressed = compress_context(tree, "Summary.", keep_recent_turns=5)
        branch = compressed.get_active_branch()
        summary_msgs = [m for m in branch if m.role == "system"]
        assert summary_msgs[0].metadata == {"type": "compression_summary"}

    def test_current_leaf_unchanged(self):
        """Compression should not change the current leaf (latest message)."""
        tree = _build_tree_with_turns(15)
        original_leaf = tree.current_leaf_id
        compress_context(tree, "Summary.", keep_recent_turns=5)
        assert tree.current_leaf_id == original_leaf

    def test_kept_messages_order_preserved(self):
        """Kept messages should remain in their original chronological order."""
        tree = _build_tree_with_turns(12)
        compressed = compress_context(tree, "Summary.", keep_recent_turns=4)
        branch = compressed.get_active_branch()
        # Skip summary, check the remaining 8 messages (4 turns x 2)
        kept = [m for m in branch if m.role != "system"]
        assert len(kept) == 8
        # Questions should be 8, 9, 10, 11
        questions = [m.content for m in kept if m.role == "user"]
        for i, q in enumerate(questions):
            assert f"Question {8 + i}" in q

    def test_in_place_modification(self):
        """compress_context modifies the tree in place and returns it."""
        tree = _build_tree_with_turns(15)
        result = compress_context(tree, "Summary.", keep_recent_turns=5)
        assert result is tree

    def test_single_turn_not_compressed(self):
        """A tree with a single turn should not be compressed."""
        tree = _build_tree_with_turns(1)
        compressed = compress_context(tree, "Summary.", keep_recent_turns=10)
        branch = compressed.get_active_branch()
        assert len(branch) == 2  # user + assistant
        assert not any("[context optimized]" in (m.content or "") for m in branch)

    def test_all_old_turns_pruned(self):
        """Every message in the pruned turns should have pruned=True."""
        tree = _build_tree_with_turns(10)
        # Capture the IDs of the first 5 turns (messages 0-9)
        branch = tree.get_active_branch()
        old_ids = [m.id for m in branch[:10]]  # first 5 turns = 10 msgs

        compress_context(tree, "Summary.", keep_recent_turns=5)

        for msg_id in old_ids:
            assert tree.messages[msg_id].pruned is True

    def test_system_messages_in_initial_turns_handled(self):
        """System messages before the first user turn don't break grouping."""
        tree = ConversationTree()
        tree.append("system", "You are a helpful assistant.")
        for i in range(10):
            tree.append("user", f"Question {i}")
            tree.append("assistant", f"Answer {i}")

        compressed = compress_context(tree, "Summary.", keep_recent_turns=5)
        branch = compressed.get_active_branch()
        # Summary + 5 kept turns (10 msgs) = 11
        assert len(branch) == 11
        # The system preamble should be pruned
        assert not any(
            m.content == "You are a helpful assistant." for m in branch
        )

    def test_tool_messages_grouped_with_assistant(self):
        """Tool responses between assistant messages belong to the same turn."""
        tree = ConversationTree()
        for i in range(8):
            tree.append("user", f"Question {i}")
            tree.append("assistant", f"Let me check tool {i}")
            tree.append("tool", f"Tool result {i}")
            tree.append("assistant", f"Answer {i}")

        compressed = compress_context(tree, "Summary.", keep_recent_turns=4)
        branch = compressed.get_active_branch()
        # 4 kept turns x 4 msgs each + 1 summary = 17
        assert len(branch) == 17
        # Check that tool messages are present in kept turns
        tool_msgs = [m for m in branch if m.role == "tool"]
        assert len(tool_msgs) == 4

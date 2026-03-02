# src/merkaba/memory/compression.py
"""Graceful in-place context compression for ConversationTree.

Compresses older turns while preserving recent conversation history.
Works by directly manipulating the message tree: pruning old messages
and inserting a summary node before the kept turns.
"""

import uuid
from datetime import datetime

from merkaba.memory.context_budget import ContextWindowConfig, estimate_tokens
from merkaba.memory.conversation import ConversationTree, Message


def should_compress(text: str, config: ContextWindowConfig) -> bool:
    """Check whether conversation text exceeds the compaction threshold.

    Returns True when estimated token count exceeds
    ``config.max_context_tokens * config.compaction_threshold``.
    """
    if not text:
        return False
    tokens = estimate_tokens(text)
    threshold = config.max_context_tokens * config.compaction_threshold
    return tokens > threshold


def _group_into_turns(branch: list[Message]) -> list[list[Message]]:
    """Group a linear message branch into conversation turns.

    A turn starts with a ``user`` message and includes all subsequent
    messages (assistant, tool, system) until the next ``user`` message.
    Messages before the first ``user`` message form their own turn
    (e.g. system preambles).
    """
    turns: list[list[Message]] = []
    current_turn: list[Message] = []

    for msg in branch:
        if msg.role == "user" and current_turn:
            turns.append(current_turn)
            current_turn = []
        current_turn.append(msg)

    if current_turn:
        turns.append(current_turn)

    return turns


def compress_context(
    tree: ConversationTree,
    summary_text: str,
    keep_recent_turns: int = 10,
) -> ConversationTree:
    """Compress older turns in-place, preserving recent ones.

    Algorithm:
    1. Get the active branch and group into turns.
    2. If there are fewer turns than ``keep_recent_turns``, return unchanged.
    3. Mark all messages in old turns as pruned.
    4. Insert a summary message before the first kept message by
       manipulating the parent chain directly.

    The tree is modified in place and returned. ``current_leaf_id``
    is NOT changed, so the caller can continue appending messages.
    """
    branch = tree.get_active_branch()
    if not branch:
        return tree

    turns = _group_into_turns(branch)

    if len(turns) <= keep_recent_turns:
        return tree  # Nothing to compress

    turns_to_prune = turns[:-keep_recent_turns]
    turns_to_keep = turns[-keep_recent_turns:]

    # Mark old messages as pruned
    for turn in turns_to_prune:
        for msg in turn:
            msg.pruned = True

    # Insert summary before the first kept message.
    # The summary takes the same parent as the first kept message,
    # then the first kept message is reparented under the summary.
    first_kept = turns_to_keep[0][0]

    summary_msg = Message(
        id=str(uuid.uuid4()),
        parent_id=first_kept.parent_id,
        role="system",
        content=f"[context optimized] {summary_text}",
        timestamp=datetime.now().isoformat(),
        metadata={"type": "compression_summary"},
    )
    tree.messages[summary_msg.id] = summary_msg
    first_kept.parent_id = summary_msg.id

    return tree

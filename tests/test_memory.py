# tests/test_memory.py
import tempfile
import os
import json
import pytest
from merkaba.memory import ConversationLog


def test_conversation_log_creation():
    with tempfile.TemporaryDirectory() as tmpdir:
        log = ConversationLog(storage_dir=tmpdir)
        assert log.storage_dir == tmpdir


def test_conversation_log_append():
    with tempfile.TemporaryDirectory() as tmpdir:
        log = ConversationLog(storage_dir=tmpdir)
        log.append("user", "Hello")
        log.append("assistant", "Hi there!")

        history = log.get_history()
        assert len(history) == 2
        assert history[0]["role"] == "user"
        assert history[0]["content"] == "Hello"


def test_conversation_log_persistence():
    with tempfile.TemporaryDirectory() as tmpdir:
        # First session
        log1 = ConversationLog(storage_dir=tmpdir, session_id="test-session")
        log1.append("user", "Hello")
        log1.save()

        # Second session loading same file
        log2 = ConversationLog(storage_dir=tmpdir, session_id="test-session")
        history = log2.get_history()
        assert len(history) == 1
        assert history[0]["content"] == "Hello"


def test_conversation_log_clear():
    with tempfile.TemporaryDirectory() as tmpdir:
        log = ConversationLog(storage_dir=tmpdir)
        log.append("user", "Hello")
        log.clear()
        assert len(log.get_history()) == 0


def test_conversation_log_get_history_with_limit():
    with tempfile.TemporaryDirectory() as tmpdir:
        log = ConversationLog(storage_dir=tmpdir)
        log.append("user", "Message 1")
        log.append("assistant", "Response 1")
        log.append("user", "Message 2")
        log.append("assistant", "Response 2")

        # Get last 2 messages
        history = log.get_history(limit=2)
        assert len(history) == 2
        assert history[0]["content"] == "Message 2"
        assert history[1]["content"] == "Response 2"

        # Get with limit=0 should return empty
        history = log.get_history(limit=0)
        assert len(history) == 0

# tests/test_protocols.py
"""TDD tests for formal Protocol definitions."""
import sys
from unittest.mock import MagicMock

if "ollama" not in sys.modules:
    sys.modules["ollama"] = MagicMock()

from merkaba.protocols import (
    ConversationBackend,
    MemoryBackend,
    Observer,
    VectorBackend,
)
from merkaba.memory.store import MemoryStore
from merkaba.memory.conversation import ConversationLog


# --- MemoryBackend protocol ---


def test_memory_backend_is_runtime_checkable():
    """MemoryBackend is @runtime_checkable so isinstance() works."""
    assert hasattr(MemoryBackend, "__protocol_attrs__") or hasattr(
        MemoryBackend, "_is_protocol"
    )


def test_memory_store_has_protocol_methods():
    """MemoryStore has the methods declared in MemoryBackend."""
    assert callable(getattr(MemoryStore, "add_fact", None))
    assert callable(getattr(MemoryStore, "get_facts", None))
    assert callable(getattr(MemoryStore, "add_decision", None))
    assert callable(getattr(MemoryStore, "get_decisions", None))


def test_memory_store_isinstance_check(tmp_path):
    """MemoryStore instance passes isinstance(x, MemoryBackend)."""
    store = MemoryStore(db_path=str(tmp_path / "test.db"))
    try:
        assert isinstance(store, MemoryBackend)
    finally:
        store.close()


def test_mock_memory_backend_conforms():
    """A minimal mock with required methods satisfies MemoryBackend."""

    class MockMemoryBackend:
        def add_fact(self, business_id, category, key, value, confidence=100, source=None, check_contradictions=False):
            return 1

        def get_facts(self, business_id, category=None, include_archived=False):
            return []

        def add_decision(self, business_id, action_type, decision, reasoning):
            return 1

        def get_decisions(self, business_id, action_type=None, include_archived=False):
            return []

    assert isinstance(MockMemoryBackend(), MemoryBackend)


# --- VectorBackend protocol ---


def test_vector_backend_is_runtime_checkable():
    """VectorBackend is @runtime_checkable."""
    assert hasattr(VectorBackend, "__protocol_attrs__") or hasattr(
        VectorBackend, "_is_protocol"
    )


def test_mock_vector_backend_conforms():
    """A mock with required methods satisfies VectorBackend."""

    class MockVectorBackend:
        def search_facts(self, query, business_id=None, limit=5):
            return []

        def search_decisions(self, query, business_id=None, limit=5):
            return []

        def search_learnings(self, query, limit=5):
            return []

        def delete_vectors(self, collection_name, ids):
            pass

    assert isinstance(MockVectorBackend(), VectorBackend)


def test_incomplete_vector_backend_fails():
    """A class missing methods does NOT satisfy VectorBackend."""

    class Incomplete:
        def search_facts(self, query, business_id=None, limit=5):
            return []

    assert not isinstance(Incomplete(), VectorBackend)


# --- ConversationBackend protocol ---


def test_conversation_backend_is_runtime_checkable():
    """ConversationBackend is @runtime_checkable."""
    assert hasattr(ConversationBackend, "__protocol_attrs__") or hasattr(
        ConversationBackend, "_is_protocol"
    )


def test_conversation_log_has_protocol_methods():
    """ConversationLog has the methods declared in ConversationBackend."""
    assert callable(getattr(ConversationLog, "append", None))
    assert callable(getattr(ConversationLog, "get_history", None))
    assert callable(getattr(ConversationLog, "save", None))


def test_conversation_log_isinstance_check(tmp_path):
    """ConversationLog instance passes isinstance(x, ConversationBackend)."""
    log = ConversationLog(storage_dir=str(tmp_path / "convos"))
    assert isinstance(log, ConversationBackend)


def test_mock_conversation_backend_conforms():
    """A minimal mock satisfies ConversationBackend."""

    class MockConversation:
        def append(self, role, content, metadata=None):
            pass

        def get_history(self, limit=None):
            return []

        def save(self):
            pass

    assert isinstance(MockConversation(), ConversationBackend)


# --- Observer protocol ---


def test_observer_is_runtime_checkable():
    """Observer is @runtime_checkable."""
    assert hasattr(Observer, "__protocol_attrs__") or hasattr(
        Observer, "_is_protocol"
    )


def test_mock_observer_conforms():
    """A mock with required methods satisfies Observer."""

    class MockObserver:
        def on_llm_call(self, model, tokens_in, tokens_out, duration):
            pass

        def on_tool_call(self, tool_name, arguments, result, duration):
            pass

        def on_error(self, component, error, context=None):
            pass

    assert isinstance(MockObserver(), Observer)


def test_incomplete_observer_fails():
    """A class missing on_error does NOT satisfy Observer."""

    class Incomplete:
        def on_llm_call(self, model, tokens_in, tokens_out, duration):
            pass

        def on_tool_call(self, tool_name, arguments, result, duration):
            pass

    assert not isinstance(Incomplete(), Observer)


# --- Negative tests ---


def test_plain_object_not_memory_backend():
    """A plain object is not a MemoryBackend."""
    assert not isinstance(object(), MemoryBackend)


def test_plain_object_not_observer():
    """A plain object is not an Observer."""
    assert not isinstance(object(), Observer)


def test_plain_object_not_conversation_backend():
    """A plain object is not a ConversationBackend."""
    assert not isinstance(object(), ConversationBackend)

# tests/test_memory_tools.py
"""Tests for the memory_search tool and its wiring helpers."""

import pytest
from unittest.mock import MagicMock

from merkaba.tools.builtin.memory_tools import (
    _memory_search,
    set_retrieval,
    set_active_business,
    memory_search,
    _retrieval_ref,
    _business_ref,
)
from merkaba.tools.base import PermissionTier


@pytest.fixture(autouse=True)
def _reset_refs():
    """Reset module-level refs before and after each test."""
    _retrieval_ref["instance"] = None
    _business_ref["id"] = None
    yield
    _retrieval_ref["instance"] = None
    _business_ref["id"] = None


class TestMemorySearchNoRetrieval:
    def test_returns_not_available_when_retrieval_is_none(self):
        """When no retrieval is wired, should return the not-available message."""
        result = _memory_search("anything")
        assert result == "Memory system not available."

    def test_tool_execute_returns_not_available(self):
        """The Tool wrapper should also surface the not-available message."""
        result = memory_search.execute(query="test")
        assert result.success is True
        assert result.output == "Memory system not available."


class TestMemorySearchNoResults:
    def test_returns_no_memories_found(self):
        """When retrieval returns empty list, should say no memories found."""
        mock_retrieval = MagicMock()
        mock_retrieval.recall.return_value = []
        set_retrieval(mock_retrieval)

        result = _memory_search("bittensor pricing")
        assert result == "No memories found for: bittensor pricing"

    def test_no_memories_found_via_tool_execute(self):
        """Same check through the Tool.execute wrapper."""
        mock_retrieval = MagicMock()
        mock_retrieval.recall.return_value = []
        set_retrieval(mock_retrieval)

        result = memory_search.execute(query="unknown topic")
        assert result.success is True
        assert "No memories found for: unknown topic" in result.output


class TestMemorySearchFormatting:
    def test_fact_formatting(self):
        """Facts should render as [Fact] category: key = value."""
        mock_retrieval = MagicMock()
        mock_retrieval.recall.return_value = [
            {"type": "fact", "category": "crypto", "key": "TAO price", "value": "$500"}
        ]
        set_retrieval(mock_retrieval)

        result = _memory_search("TAO")
        assert result == "[Fact] crypto: TAO price = $500"

    def test_decision_formatting(self):
        """Decisions should render as [Decision] decision -- reasoning."""
        mock_retrieval = MagicMock()
        mock_retrieval.recall.return_value = [
            {"type": "decision", "decision": "Use SN59", "reasoning": "Best fit for agents"}
        ]
        set_retrieval(mock_retrieval)

        result = _memory_search("subnet")
        assert "[Decision] Use SN59" in result
        assert "Best fit for agents" in result

    def test_learning_formatting(self):
        """Learnings should render as [Learning] insight."""
        mock_retrieval = MagicMock()
        mock_retrieval.recall.return_value = [
            {"type": "learning", "insight": "Always seed memory before testing"}
        ]
        set_retrieval(mock_retrieval)

        result = _memory_search("testing tips")
        assert result == "[Learning] Always seed memory before testing"

    def test_mixed_result_types(self):
        """Multiple result types should each get the correct prefix."""
        mock_retrieval = MagicMock()
        mock_retrieval.recall.return_value = [
            {"type": "fact", "category": "infra", "key": "db", "value": "SQLite"},
            {"type": "decision", "decision": "Use WAL mode", "reasoning": "concurrency"},
            {"type": "learning", "insight": "WAL improves read throughput"},
        ]
        set_retrieval(mock_retrieval)

        result = _memory_search("database")
        lines = result.split("\n")
        assert len(lines) == 3
        assert lines[0].startswith("[Fact]")
        assert lines[1].startswith("[Decision]")
        assert lines[2].startswith("[Learning]")

    def test_missing_fields_default_to_empty(self):
        """If optional fields are missing from a result dict, they default to empty strings."""
        mock_retrieval = MagicMock()
        mock_retrieval.recall.return_value = [
            {"type": "fact"},  # no category, key, or value
        ]
        set_retrieval(mock_retrieval)

        result = _memory_search("sparse")
        assert result == "[Fact] :  = "

    def test_unknown_type_produces_no_line(self):
        """Result dicts with unrecognized types are silently skipped."""
        mock_retrieval = MagicMock()
        mock_retrieval.recall.return_value = [
            {"type": "unknown_type", "data": "something"},
        ]
        set_retrieval(mock_retrieval)

        result = _memory_search("test")
        # No matching branch, so lines list is empty -> empty string from join
        assert result == ""


class TestBusinessIdScoping:
    def test_recall_called_with_business_id(self):
        """set_active_business should propagate business_id to recall()."""
        mock_retrieval = MagicMock()
        mock_retrieval.recall.return_value = []
        set_retrieval(mock_retrieval)
        set_active_business(42)

        _memory_search("anything")

        mock_retrieval.recall.assert_called_once_with(
            "anything", business_id=42, limit=5
        )

    def test_recall_called_with_none_when_no_business(self):
        """Without set_active_business, business_id should be None."""
        mock_retrieval = MagicMock()
        mock_retrieval.recall.return_value = []
        set_retrieval(mock_retrieval)

        _memory_search("query")

        mock_retrieval.recall.assert_called_once_with(
            "query", business_id=None, limit=5
        )

    def test_clear_active_business(self):
        """Clearing business ID should revert to None."""
        mock_retrieval = MagicMock()
        mock_retrieval.recall.return_value = []
        set_retrieval(mock_retrieval)

        set_active_business(7)
        set_active_business(None)

        _memory_search("q")

        mock_retrieval.recall.assert_called_once_with(
            "q", business_id=None, limit=5
        )


class TestSetRetrieval:
    def test_wires_instance(self):
        """set_retrieval should store the instance in the module ref."""
        sentinel = object()
        set_retrieval(sentinel)
        assert _retrieval_ref["instance"] is sentinel

    def test_overwrite_instance(self):
        """Calling set_retrieval again should replace the previous instance."""
        first = MagicMock()
        second = MagicMock()
        set_retrieval(first)
        set_retrieval(second)
        assert _retrieval_ref["instance"] is second


class TestSetActiveBusiness:
    def test_sets_business_id(self):
        """set_active_business should update the ref."""
        set_active_business(99)
        assert _business_ref["id"] == 99

    def test_clears_business_id(self):
        """Passing None should clear the ref."""
        set_active_business(10)
        set_active_business(None)
        assert _business_ref["id"] is None


class TestLimitParameter:
    def test_custom_limit_forwarded(self):
        """The limit parameter should be forwarded to retrieval.recall()."""
        mock_retrieval = MagicMock()
        mock_retrieval.recall.return_value = []
        set_retrieval(mock_retrieval)

        _memory_search("topic", limit=10)

        mock_retrieval.recall.assert_called_once_with(
            "topic", business_id=None, limit=10
        )

    def test_default_limit_is_five(self):
        """Without explicit limit, default should be 5."""
        mock_retrieval = MagicMock()
        mock_retrieval.recall.return_value = []
        set_retrieval(mock_retrieval)

        _memory_search("topic")

        mock_retrieval.recall.assert_called_once_with(
            "topic", business_id=None, limit=5
        )


class TestToolMetadata:
    def test_tool_name(self):
        assert memory_search.name == "memory_search"

    def test_permission_tier(self):
        assert memory_search.permission_tier == PermissionTier.SAFE

    def test_parameters_require_query(self):
        assert "query" in memory_search.parameters["properties"]
        assert "query" in memory_search.parameters["required"]

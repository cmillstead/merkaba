# tests/test_domain_worker_fallbacks.py
"""Tests for JSON fallback paths in domain workers.

When the LLM returns plain text instead of JSON, each worker has
except (json.JSONDecodeError, TypeError) fallback logic that wraps the
raw response into a structured dict. These paths are tested here.
"""

import json
from unittest.mock import MagicMock

import pytest

from merkaba.orchestration.content_worker import ContentWorker
from merkaba.orchestration.ecommerce_worker import EcommerceWorker
from merkaba.orchestration.support_worker import SupportWorker
from merkaba.orchestration.workers import WorkerResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_task(task_type: str, payload: dict) -> dict:
    return {
        "id": 1,
        "name": "Test Task",
        "task_type": task_type,
        "payload": payload,
    }


# ===========================================================================
# ContentWorker
# ===========================================================================


class TestContentWorkerFallbacks:
    """ContentWorker JSON fallback paths."""

    def _worker(self, llm_return: str) -> ContentWorker:
        w = ContentWorker()
        w._ask_llm = MagicMock(return_value=llm_return)
        return w

    # -- _draft_post fallback -----------------------------------------------

    def test_draft_post_json_fallback(self):
        """When LLM returns plain text, output wraps it with topic as title."""
        plain = "Here is a great article about gardening."
        w = self._worker(plain)
        task = _make_task("content", {"action": "draft_post", "topic": "gardening"})

        result = w.execute(task)

        assert result.success is True
        assert result.output["title"] == "gardening"
        assert result.output["content"] == plain
        assert result.output["summary"] == ""

    def test_draft_post_json_fallback_facts_learned(self):
        """Fallback output is still persisted as a fact."""
        plain = "Draft content here."
        w = self._worker(plain)
        task = _make_task("content", {"action": "draft_post", "topic": "seo"})

        result = w.execute(task)

        assert len(result.facts_learned) == 1
        fact = result.facts_learned[0]
        assert fact["category"] == "content"
        assert fact["key"] == "draft:seo"
        # The fact value is the JSON-serialized fallback dict
        parsed = json.loads(fact["value"])
        assert parsed["title"] == "seo"
        assert parsed["content"] == plain

    def test_draft_post_valid_json_still_works(self):
        """Sanity check: valid JSON is parsed normally."""
        valid = json.dumps({"title": "My Title", "content": "Body", "summary": "Sum"})
        w = self._worker(valid)
        task = _make_task("content", {"action": "draft_post", "topic": "anything"})

        result = w.execute(task)

        assert result.success is True
        assert result.output["title"] == "My Title"
        assert result.output["content"] == "Body"
        assert result.output["summary"] == "Sum"

    # -- _review_content fallback -------------------------------------------

    def test_review_content_json_fallback(self):
        """Plain text review wraps into raw_response, no decisions."""
        plain = "The draft looks fine overall."
        w = self._worker(plain)
        task = _make_task("content", {"action": "review_content", "draft": "some draft"})

        result = w.execute(task)

        assert result.success is True
        assert result.output == {"raw_response": plain}
        # No suggestions means no decisions
        assert result.decisions_made == []

    # -- _analyze_performance fallback --------------------------------------

    def test_analyze_performance_json_fallback(self):
        """Plain text performance analysis wraps into raw_response."""
        plain = "Performance has been steady this quarter."
        w = self._worker(plain)
        task = _make_task("content", {"action": "analyze_performance"})

        result = w.execute(task)

        assert result.success is True
        assert result.output == {"raw_response": plain}
        assert result.decisions_made == []

    # -- Unknown action -----------------------------------------------------

    def test_unknown_action(self):
        """Unknown action returns failure with descriptive error."""
        w = ContentWorker()
        task = _make_task("content", {"action": "nonexistent"})

        result = w.execute(task)

        assert result.success is False
        assert "Unknown content action: nonexistent" in result.error

    def test_none_action(self):
        """action=None returns failure."""
        w = ContentWorker()
        task = _make_task("content", {})

        result = w.execute(task)

        assert result.success is False
        assert "Unknown content action: None" in result.error

    # -- Handler exception --------------------------------------------------

    def test_handler_exception_caught(self):
        """Exception inside a handler is caught and returned as failure."""
        w = ContentWorker()
        w._ask_llm = MagicMock(side_effect=RuntimeError("LLM is down"))
        task = _make_task("content", {"action": "draft_post", "topic": "test"})

        result = w.execute(task)

        assert result.success is False
        assert "LLM is down" in result.error


# ===========================================================================
# EcommerceWorker
# ===========================================================================


class TestEcommerceWorkerFallbacks:
    """EcommerceWorker JSON fallback paths."""

    def _worker(self, llm_return: str) -> EcommerceWorker:
        w = EcommerceWorker()
        w._ask_llm = MagicMock(return_value=llm_return)
        return w

    # -- _review_pricing fallback -------------------------------------------

    def test_review_pricing_json_fallback(self):
        """Plain text pricing review wraps into raw_response, no decisions."""
        plain = "Prices look competitive for this season."
        w = self._worker(plain)
        task = _make_task("ecommerce", {"action": "review_pricing"})

        result = w.execute(task)

        assert result.success is True
        assert result.output == {"raw_response": plain}
        # No recommendations means no decisions
        assert result.decisions_made == []

    def test_review_pricing_valid_json(self):
        """Sanity check: valid JSON is parsed normally."""
        valid = json.dumps({
            "recommendations": [
                {"listing_key": "L1", "current_price": 10, "suggested_price": 12, "reasoning": "underpriced"}
            ]
        })
        w = self._worker(valid)
        task = _make_task("ecommerce", {"action": "review_pricing"})

        result = w.execute(task)

        assert result.success is True
        assert len(result.output["recommendations"]) == 1
        # Price changed, so one decision
        assert len(result.decisions_made) == 1

    # -- Unknown action -----------------------------------------------------

    def test_unknown_action(self):
        """Unknown ecommerce action returns failure."""
        w = EcommerceWorker()
        task = _make_task("ecommerce", {"action": "bogus"})

        result = w.execute(task)

        assert result.success is False
        assert "Unknown ecommerce action: bogus" in result.error

    def test_none_action(self):
        """action=None returns failure."""
        w = EcommerceWorker()
        task = _make_task("ecommerce", {})

        result = w.execute(task)

        assert result.success is False
        assert "Unknown ecommerce action: None" in result.error

    # -- Handler exception --------------------------------------------------

    def test_handler_exception_caught(self):
        """Exception inside a handler is caught and returned as failure."""
        w = EcommerceWorker()
        w._ask_llm = MagicMock(side_effect=ValueError("adapter exploded"))
        task = _make_task("ecommerce", {"action": "review_pricing"})

        result = w.execute(task)

        assert result.success is False
        assert "adapter exploded" in result.error


# ===========================================================================
# SupportWorker
# ===========================================================================


class TestSupportWorkerFallbacks:
    """SupportWorker JSON fallback paths."""

    def _worker(self, llm_return: str) -> SupportWorker:
        w = SupportWorker()
        w._ask_llm = MagicMock(return_value=llm_return)
        return w

    # -- _triage_ticket fallback --------------------------------------------

    def test_triage_ticket_json_fallback(self):
        """Plain text triage defaults to medium priority, general category."""
        plain = "This ticket is about a billing issue."
        w = self._worker(plain)
        task = _make_task("support", {
            "action": "triage_ticket",
            "description": "I was charged twice",
            "ticket_id": "T-42",
        })

        result = w.execute(task)

        assert result.success is True
        assert result.output["priority"] == "medium"
        assert result.output["category"] == "general"
        assert result.output["summary"] == plain

    def test_triage_ticket_fallback_fact_stored(self):
        """Fallback triage data is stored as a fact with the ticket_id."""
        plain = "Needs further review."
        w = self._worker(plain)
        task = _make_task("support", {
            "action": "triage_ticket",
            "description": "broken widget",
            "ticket_id": "T-99",
        })

        result = w.execute(task)

        assert len(result.facts_learned) == 1
        fact = result.facts_learned[0]
        assert fact["key"] == "ticket:T-99"
        parsed = json.loads(fact["value"])
        assert parsed["priority"] == "medium"

    # -- _draft_response fallback -------------------------------------------

    def test_draft_response_json_fallback(self):
        """Plain text response wraps with neutral tone, no follow-up."""
        plain = "We apologize for the inconvenience."
        w = self._worker(plain)
        task = _make_task("support", {
            "action": "draft_response",
            "ticket": {"ticket_id": "T-10", "description": "product broken"},
        })

        result = w.execute(task)

        assert result.success is True
        assert result.output["response"] == plain
        assert result.output["tone"] == "neutral"
        assert result.output["follow_up_needed"] is False

    def test_draft_response_fallback_fact_stored(self):
        """Fallback response data is stored as a fact."""
        plain = "Please try restarting."
        w = self._worker(plain)
        task = _make_task("support", {
            "action": "draft_response",
            "ticket": {"ticket_id": "T-77", "description": "app crashes"},
        })

        result = w.execute(task)

        assert len(result.facts_learned) == 1
        fact = result.facts_learned[0]
        assert fact["key"] == "response:T-77"
        parsed = json.loads(fact["value"])
        assert parsed["response"] == plain
        assert parsed["tone"] == "neutral"

    # -- _analyze_satisfaction fallback --------------------------------------

    def test_analyze_satisfaction_json_fallback(self):
        """Plain text satisfaction analysis wraps into raw_response."""
        plain = "Overall satisfaction is good."
        w = self._worker(plain)
        task = _make_task("support", {"action": "analyze_satisfaction"})

        result = w.execute(task)

        assert result.success is True
        assert result.output == {"raw_response": plain}
        assert result.decisions_made == []

    # -- Unknown action -----------------------------------------------------

    def test_unknown_action(self):
        """Unknown support action returns failure."""
        w = SupportWorker()
        task = _make_task("support", {"action": "delete_everything"})

        result = w.execute(task)

        assert result.success is False
        assert "Unknown support action: delete_everything" in result.error

    def test_none_action(self):
        """action=None returns failure."""
        w = SupportWorker()
        task = _make_task("support", {})

        result = w.execute(task)

        assert result.success is False
        assert "Unknown support action: None" in result.error

    # -- Handler exception --------------------------------------------------

    def test_handler_exception_caught(self):
        """Exception inside a handler is caught and returned as failure."""
        w = SupportWorker()
        w._ask_llm = MagicMock(side_effect=ConnectionError("timeout"))
        task = _make_task("support", {
            "action": "triage_ticket",
            "description": "test",
        })

        result = w.execute(task)

        assert result.success is False
        assert "timeout" in result.error

"""Tests for the generic support worker."""

import json
from unittest.mock import patch

import pytest

from merkaba.orchestration.workers import WorkerResult


@pytest.fixture
def worker():
    from merkaba.orchestration.support_worker import SupportWorker
    return SupportWorker(business_id=1)


class TestSupportWorkerTriage:
    def test_triage_returns_parsed_json(self, worker):
        result_json = json.dumps({"priority": "high", "category": "billing", "summary": "Refund request"})
        with patch.object(worker, "_ask_llm", return_value=result_json):
            result = worker.execute({"name": "triage", "task_type": "support", "payload": {"action": "triage_ticket", "description": "I want a refund", "ticket_id": "T1"}})
        assert result.success
        assert result.output["priority"] == "high"

    def test_triage_handles_non_json_response(self, worker):
        with patch.object(worker, "_ask_llm", return_value="this is not json"):
            result = worker.execute({"name": "triage", "task_type": "support", "payload": {"action": "triage_ticket", "description": "Help", "ticket_id": "T2"}})
        assert result.success
        assert result.output["priority"] == "medium"


class TestSupportWorkerDraftResponse:
    def test_draft_response_returns_parsed_json(self, worker):
        result_json = json.dumps({"response": "We'll help", "tone": "empathetic", "follow_up_needed": False})
        with patch.object(worker, "_ask_llm", return_value=result_json):
            result = worker.execute({"payload": {"action": "draft_response", "ticket": {"description": "Issue"}}})
        assert result.success
        assert "response" in result.output


class TestSupportWorkerEscalate:
    def test_escalate_requires_ticket_id_and_reason(self, worker):
        result = worker.execute({"payload": {"action": "escalate_ticket"}})
        assert not result.success
        assert "Missing" in result.error

    def test_escalate_returns_needs_approval(self, worker):
        result = worker.execute({"payload": {"action": "escalate_ticket", "ticket_id": "T1", "reason": "Urgent"}})
        assert result.success
        assert len(result.needs_approval) == 1


class TestSupportWorkerUnknownAction:
    def test_unknown_action_fails(self, worker):
        result = worker.execute({"payload": {"action": "nonexistent"}})
        assert not result.success
        assert "Unknown" in result.error

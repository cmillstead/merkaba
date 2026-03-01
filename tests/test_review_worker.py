# tests/test_review_worker.py
"""Tests for ReviewWorker."""

import sys
from unittest.mock import MagicMock, patch

import pytest

sys.modules.setdefault("ollama", MagicMock())

from merkaba.orchestration.review_worker import ReviewWorker
from merkaba.orchestration.workers import WORKER_REGISTRY


def _make_task(output_text="def foo(): pass", criteria=None, task_spec=None):
    payload = {"output_text": output_text}
    if criteria is not None:
        payload["review_criteria"] = criteria
    if task_spec is not None:
        payload["task_spec"] = task_spec
    return {
        "id": 0,
        "name": "Test review",
        "task_type": "review",
        "payload": payload,
    }


class TestReviewWorkerRegistration:

    def test_review_worker_registered(self):
        # "review" must be in the registry; the exact class may be overridden
        # by extension packages (e.g. friday-etsy) that also register "review"
        assert "review" in WORKER_REGISTRY

    def test_review_worker_is_a_worker_subclass(self):
        from merkaba.orchestration.workers import Worker
        assert issubclass(ReviewWorker, Worker)


class TestReviewWorkerExecute:

    def test_successful_review(self):
        worker = ReviewWorker()
        with patch.object(worker, "_ask_llm", return_value="Looks good. No issues."):
            result = worker.execute(_make_task())
        assert result.success is True
        assert result.output["review"] == "Looks good. No issues."

    def test_review_with_criteria(self):
        worker = ReviewWorker()
        captured_prompt = None

        def capture_llm(prompt, **kwargs):
            nonlocal captured_prompt
            captured_prompt = prompt
            return "Review complete."

        with patch.object(worker, "_ask_llm", side_effect=capture_llm):
            result = worker.execute(_make_task(criteria="Check error handling"))
        assert result.success is True
        assert "Check error handling" in captured_prompt

    def test_review_with_task_spec(self):
        worker = ReviewWorker()
        captured_prompt = None

        def capture_llm(prompt, **kwargs):
            nonlocal captured_prompt
            captured_prompt = prompt
            return "Review complete."

        with patch.object(worker, "_ask_llm", side_effect=capture_llm):
            result = worker.execute(_make_task(task_spec="Build a parser"))
        assert result.success is True
        assert "Build a parser" in captured_prompt

    def test_empty_output_text_fails(self):
        worker = ReviewWorker()
        task = _make_task(output_text="")
        result = worker.execute(task)
        assert result.success is False
        assert "No code" in result.error

    def test_no_payload_fails(self):
        worker = ReviewWorker()
        task = {"id": 0, "name": "No payload", "task_type": "review", "payload": {}}
        result = worker.execute(task)
        assert result.success is False

    def test_llm_failure_returns_error(self):
        worker = ReviewWorker()
        with patch.object(worker, "_ask_llm", side_effect=RuntimeError("LLM down")):
            result = worker.execute(_make_task())
        assert result.success is False
        assert "LLM" in result.error

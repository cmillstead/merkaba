# tests/test_learnings.py
import sys
import tempfile
import os
from unittest.mock import MagicMock

import pytest

from merkaba.memory.store import MemoryStore
from merkaba.orchestration.workers import WorkerResult
from merkaba.orchestration.learnings import LearningExtractor


@pytest.fixture
def memory():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "memory.db")
        store = MemoryStore(db_path=db_path)
        yield store
        store.close()


@pytest.fixture
def extractor(memory):
    return LearningExtractor(memory_store=memory, batch_threshold=3)


@pytest.fixture
def mock_ollama():
    """Inject a mock ollama module so the lazy import picks it up."""
    mock = MagicMock()
    original = sys.modules.get("ollama")
    sys.modules["ollama"] = mock
    yield mock
    if original is not None:
        sys.modules["ollama"] = original
    else:
        del sys.modules["ollama"]


def _make_task(task_id=1, name="Test Task", task_type="check", business_id=None):
    return {"id": task_id, "name": name, "task_type": task_type, "business_id": business_id}


# --- Rule-based extraction ---


def test_no_learning_on_success(extractor):
    task = _make_task()
    result = WorkerResult(success=True, output={"status": "ok"})
    learnings = extractor.process(task, result)
    assert learnings == []


def test_learning_on_failure(extractor, memory):
    task = _make_task()
    result = WorkerResult(success=False, output={}, error="ConnectionError: refused")
    learnings = extractor.process(task, result)

    assert len(learnings) == 1
    assert learnings[0]["category"] == "failure_pattern"
    assert "ConnectionError" in learnings[0]["insight"]

    # Verify it was stored in memory
    stored = memory.get_learnings(category="failure_pattern")
    assert len(stored) == 1


def test_no_duplicate_failure_learning(extractor, memory):
    task = _make_task()
    result = WorkerResult(success=False, output={}, error="ConnectionError: refused")

    # First failure — should produce a learning
    learnings1 = extractor.process(task, result)
    assert len(learnings1) == 1

    # Same error again — should NOT produce a duplicate
    learnings2 = extractor.process(task, result)
    assert len(learnings2) == 0


def test_different_errors_produce_separate_learnings(extractor, memory):
    task = _make_task()
    r1 = WorkerResult(success=False, output={}, error="ConnectionError: refused")
    r2 = WorkerResult(success=False, output={}, error="TimeoutError: deadline exceeded")

    extractor.process(task, r1)
    extractor.process(task, r2)

    stored = memory.get_learnings(category="failure_pattern")
    assert len(stored) == 2


# --- Batch LLM extraction ---


def test_llm_extraction_triggered_at_threshold(mock_ollama, extractor):
    mock_ollama.chat.return_value = {
        "message": {"content": '{"learnings": [{"category": "optimization", "insight": "Batch tasks are faster", "evidence": "3 tasks", "confidence": 60}]}'}
    }

    task = _make_task()
    result = WorkerResult(success=True, output={"status": "ok"})

    # Process batch_threshold (3) tasks
    for i in range(3):
        learnings = extractor.process(_make_task(task_id=i), result)

    # The third call should have triggered LLM extraction
    mock_ollama.chat.assert_called_once()
    assert any(l["category"] == "optimization" for l in learnings)


def test_llm_extraction_not_triggered_below_threshold(mock_ollama, extractor):
    task = _make_task()
    result = WorkerResult(success=True, output={"status": "ok"})

    # Only 2 tasks (below threshold of 3)
    extractor.process(_make_task(task_id=1), result)
    extractor.process(_make_task(task_id=2), result)

    mock_ollama.chat.assert_not_called()


def test_llm_extraction_error_handled(mock_ollama, extractor):
    mock_ollama.chat.side_effect = Exception("Model not available")

    task = _make_task()
    result = WorkerResult(success=True, output={"status": "ok"})

    # Process threshold tasks — LLM will fail but should not raise
    for i in range(3):
        learnings = extractor.process(_make_task(task_id=i), result)

    # No crash, no learnings from LLM
    assert learnings == []


def test_counter_resets_after_batch(mock_ollama, extractor):
    mock_ollama.chat.return_value = {
        "message": {"content": '{"learnings": []}'}
    }

    task = _make_task()
    result = WorkerResult(success=True, output={"status": "ok"})

    # First batch of 3
    for i in range(3):
        extractor.process(_make_task(task_id=i), result)
    assert mock_ollama.chat.call_count == 1

    # Second batch of 3
    for i in range(3, 6):
        extractor.process(_make_task(task_id=i), result)
    assert mock_ollama.chat.call_count == 2

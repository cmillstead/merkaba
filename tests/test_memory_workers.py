# tests/test_memory_workers.py
import json
import tempfile
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from merkaba.memory.store import MemoryStore
from merkaba.orchestration.workers import WorkerResult


@pytest.fixture
def store(tmp_path):
    s = MemoryStore(db_path=str(tmp_path / "memory.db"))
    yield s
    s.close()


def test_memory_decay_worker_executes(store):
    """MemoryDecayWorker runs decay and returns success."""
    from merkaba.orchestration.memory_workers import MemoryDecayWorker

    bid = store.add_business("Shop", "ecommerce")
    fid = store.add_fact(bid, "pricing", "avg", "4.99")
    old_time = (datetime.now() - timedelta(days=30)).isoformat()
    store._conn.execute("UPDATE facts SET last_accessed = ? WHERE id = ?", (old_time, fid))
    store._conn.commit()

    worker = MemoryDecayWorker(memory_store=store)
    result = worker.execute({"id": 1, "name": "memory_decay", "task_type": "memory_decay", "payload": {}})

    assert isinstance(result, WorkerResult)
    assert result.success is True
    assert result.output["decayed"] >= 1

    fact = store.get_fact(fid)
    assert fact["relevance_score"] < 1.0


def test_memory_consolidation_worker_executes(store):
    """MemoryConsolidationWorker runs consolidation and returns success."""
    from merkaba.orchestration.memory_workers import MemoryConsolidationWorker

    bid = store.add_business("Shop", "ecommerce")
    for i in range(6):
        store.add_fact(bid, "pricing", f"item_{i}", f"${i}.99")

    mock_llm = MagicMock()
    mock_llm.chat.return_value = MagicMock(content="Items range from $0.99 to $5.99.")

    worker = MemoryConsolidationWorker(memory_store=store, llm=mock_llm)
    result = worker.execute({"id": 2, "name": "memory_consolidate", "task_type": "memory_consolidate", "payload": {}})

    assert isinstance(result, WorkerResult)
    assert result.success is True
    assert result.output["summaries"] >= 1
    assert result.output["archived"] >= 5


def test_register_memory_jobs_creates_tasks(tmp_path):
    """register_memory_jobs creates decay and consolidation tasks in the queue."""
    from merkaba.orchestration.queue import TaskQueue
    from merkaba.orchestration.memory_workers import register_memory_jobs

    queue = TaskQueue(db_path=str(tmp_path / "tasks.db"))
    register_memory_jobs(queue)

    tasks = queue.list_tasks()
    task_names = {t["name"] for t in tasks}
    assert "memory_decay" in task_names
    assert "memory_consolidate" in task_names

    decay_task = next(t for t in tasks if t["name"] == "memory_decay")
    assert decay_task["schedule"] == "0 3 * * *"

    consolidate_task = next(t for t in tasks if t["name"] == "memory_consolidate")
    assert consolidate_task["schedule"] == "0 4 * * 0"


def test_register_memory_jobs_idempotent(tmp_path):
    """Calling register_memory_jobs twice does not create duplicates."""
    from merkaba.orchestration.queue import TaskQueue
    from merkaba.orchestration.memory_workers import register_memory_jobs

    queue = TaskQueue(db_path=str(tmp_path / "tasks.db"))
    register_memory_jobs(queue)
    register_memory_jobs(queue)

    tasks = queue.list_tasks()
    decay_tasks = [t for t in tasks if t["name"] == "memory_decay"]
    assert len(decay_tasks) == 1


def test_full_memory_lifecycle_integration(tmp_path):
    """End-to-end: extract with relationships, consolidate, decay, recall."""
    from merkaba.memory.store import MemoryStore
    from merkaba.memory.retrieval import MemoryRetrieval
    from merkaba.memory.lifecycle import SessionExtractor, MemoryConsolidationJob, MemoryDecayJob

    store = MemoryStore(db_path=str(tmp_path / "memory.db"))
    retrieval = MemoryRetrieval(store=store, vectors=None)

    bid = store.add_business("Corp", "enterprise")

    mock_llm = MagicMock()
    mock_llm.chat.return_value = MagicMock(
        content=json.dumps({
            "facts": [
                {"category": "org", "key": "engineering", "value": "Engineering builds core platform", "confidence": 80},
                {"category": "org", "key": "marketing", "value": "Marketing runs campaigns and ads", "confidence": 80},
                {"category": "org", "key": "sales", "value": "Sales handles enterprise accounts", "confidence": 80},
                {"category": "org", "key": "finance", "value": "Finance manages budgets quarterly", "confidence": 80},
                {"category": "org", "key": "support", "value": "Support triages customer tickets", "confidence": 80},
                {"category": "org", "key": "design", "value": "Design creates user interfaces", "confidence": 80},
            ],
            "relationships": [
                {"entity": "Alice", "entity_type": "person", "relation": "manages", "related_entity": "auth team", "related_type": "team"},
            ],
        })
    )

    extractor = SessionExtractor(llm=mock_llm, store=store)
    extractor.extract(
        [{"role": "user", "content": "Tell me about the org structure"}],
        business_id=bid,
    )

    rels = store.get_relationships(bid)
    assert len(rels) == 1

    results = retrieval.recall("Alice", business_id=bid)
    types = {r["type"] for r in results}
    assert "relationship" in types

    mock_llm.chat.return_value = MagicMock(content="Teams 0-5 do various stuff.")
    job = MemoryConsolidationJob(store=store, llm=mock_llm)
    stats = job.run()
    assert stats["summaries"] >= 1

    decay = MemoryDecayJob(store=store)
    decay_stats = decay.run()
    assert "decayed" in decay_stats

    store.close()

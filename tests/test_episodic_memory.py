# tests/test_episodic_memory.py
"""Tests for episodic memory: store, retrieval, and stats."""

import sys
from unittest.mock import MagicMock

import pytest

# Mock ollama before any merkaba imports
sys.modules.setdefault("ollama", MagicMock())

from merkaba.memory.store import MemoryStore
from merkaba.memory.retrieval import MemoryRetrieval


@pytest.fixture
def store(tmp_path):
    s = MemoryStore(db_path=str(tmp_path / "mem.db"))
    yield s
    s.close()


@pytest.fixture
def biz(store):
    """Create a test business and return its id."""
    return store.add_business("TestBiz", "ecommerce")


@pytest.fixture
def biz2(store):
    """Create a second test business and return its id."""
    return store.add_business("OtherBiz", "content")


def test_add_episode(store, biz):
    eid = store.add_episode(
        business_id=biz,
        task_type="research",
        task_id=1,
        summary="Researched competitor pricing",
        outcome="success",
        outcome_details="Found 5 competitors",
        key_decisions=["Focus on mid-range"],
    )
    assert isinstance(eid, int)
    assert eid > 0


def test_get_episodes_filters_by_business(store, biz, biz2):
    store.add_episode(biz, "research", 1, "Biz1 episode", "success")
    store.add_episode(biz2, "content", 2, "Biz2 episode", "success")

    eps = store.get_episodes(business_id=biz)
    assert len(eps) == 1
    assert eps[0]["summary"] == "Biz1 episode"

    eps2 = store.get_episodes(business_id=biz2)
    assert len(eps2) == 1
    assert eps2[0]["summary"] == "Biz2 episode"


def test_get_episodes_filters_by_task_type(store, biz):
    store.add_episode(biz, "research", 1, "Research ep", "success")
    store.add_episode(biz, "content", 2, "Content ep", "failure")

    eps = store.get_episodes(business_id=biz, task_type="research")
    assert len(eps) == 1
    assert eps[0]["task_type"] == "research"


def test_get_episodes_orders_by_recency(store, biz):
    store.add_episode(biz, "research", 1, "First", "success")
    store.add_episode(biz, "research", 2, "Second", "success")
    store.add_episode(biz, "research", 3, "Third", "success")

    eps = store.get_episodes(business_id=biz)
    assert eps[0]["summary"] == "Third"
    assert eps[1]["summary"] == "Second"
    assert eps[2]["summary"] == "First"


def test_get_episode_by_id(store, biz):
    eid = store.add_episode(biz, "research", 1, "Specific episode", "success",
                            key_decisions=["dec1", "dec2"], tags=["tag1"])
    ep = store.get_episode(eid)
    assert ep is not None
    assert ep["summary"] == "Specific episode"
    assert ep["key_decisions"] == ["dec1", "dec2"]
    assert ep["tags"] == ["tag1"]


def test_get_episode_missing(store):
    assert store.get_episode(9999) is None


def test_stats_includes_episodes(store, biz):
    store.add_episode(biz, "research", 1, "Episode 1", "success")
    store.add_episode(biz, "content", 2, "Episode 2", "failure")

    stats = store.stats()
    assert "episodes" in stats
    assert stats["episodes"] == 2


def test_recall_includes_episodes(store, biz):
    # Add a fact so keyword search has something to match
    store.add_fact(biz, "pricing", "avg_price", "29.99")

    # Add an episode
    store.add_episode(biz, "research", 1, "Researched pricing trends", "success")

    retrieval = MemoryRetrieval(store=store, vectors=None)
    results = retrieval.recall("pricing", business_id=biz)

    types = [r["type"] for r in results]
    assert "episode" in types
    episode_results = [r for r in results if r["type"] == "episode"]
    assert episode_results[0]["summary"] == "Researched pricing trends"

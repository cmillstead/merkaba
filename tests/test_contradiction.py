# tests/test_contradiction.py
"""Tests for contradiction detection and deduplication."""

import sys
from unittest.mock import MagicMock, patch

import pytest

# Mock ollama before any merkaba imports
sys.modules.setdefault("ollama", MagicMock())

from merkaba.memory.store import MemoryStore
from merkaba.memory.contradiction import ContradictionDetector, _keyword_overlap


@pytest.fixture
def store(tmp_path):
    s = MemoryStore(db_path=str(tmp_path / "mem.db"))
    yield s
    s.close()


@pytest.fixture
def biz(store):
    return store.add_business("TestBiz", "ecommerce")


@pytest.fixture
def detector(store):
    return ContradictionDetector(store=store)


def test_deduplicate_keeps_most_recent(detector):
    results = [
        {"type": "fact", "category": "pricing", "key": "price", "value": "old price is 10",
         "created_at": "2026-01-01T00:00:00"},
        {"type": "fact", "category": "pricing", "key": "price", "value": "old price is 15",
         "created_at": "2026-02-01T00:00:00"},
    ]
    deduped = detector.deduplicate_by_recency(results)
    assert len(deduped) == 1
    assert deduped[0]["created_at"] == "2026-02-01T00:00:00"


def test_deduplicate_preserves_dissimilar(detector):
    results = [
        {"type": "fact", "category": "pricing", "key": "price", "value": "widget costs ten dollars",
         "created_at": "2026-01-01T00:00:00"},
        {"type": "fact", "category": "shipping", "key": "carrier", "value": "fedex delivers packages overnight",
         "created_at": "2026-02-01T00:00:00"},
    ]
    deduped = detector.deduplicate_by_recency(results)
    assert len(deduped) == 2


def test_keyword_overlap_calculation():
    # Identical texts should have overlap of 1.0
    assert _keyword_overlap("the quick brown fox", "the quick brown fox") == 1.0
    # Completely different texts
    assert _keyword_overlap("alpha beta gamma", "delta epsilon zeta") == 0.0
    # Partial overlap
    overlap = _keyword_overlap("price is ten dollars", "price was fifteen dollars")
    assert 0.0 < overlap < 1.0


def test_check_on_write_finds_contradiction(store, biz, detector):
    # Add an existing fact
    store.add_fact(biz, "pricing", "widget_price", "widget price is 10 dollars")

    # Mock LLM to say YES contradiction
    mock_llm = MagicMock()
    mock_response = MagicMock()
    mock_response.content = "YES"
    mock_llm.chat_with_retry.return_value = mock_response
    detector._llm = mock_llm

    contradicted = detector.check_on_write(
        biz, "pricing", "widget_price", "widget price is 20 dollars"
    )
    assert len(contradicted) == 1
    assert contradicted[0]["value"] == "widget price is 10 dollars"


def test_check_on_write_no_contradiction(store, biz, detector):
    store.add_fact(biz, "pricing", "widget_price", "widget price is 10 dollars")

    mock_llm = MagicMock()
    mock_response = MagicMock()
    mock_response.content = "NO"
    mock_llm.chat_with_retry.return_value = mock_response
    detector._llm = mock_llm

    contradicted = detector.check_on_write(
        biz, "pricing", "widget_price", "widget price is 10 dollars confirmed"
    )
    assert len(contradicted) == 0


def test_check_on_write_no_existing_facts(store, biz, detector):
    contradicted = detector.check_on_write(
        biz, "pricing", "widget_price", "widget price is 10 dollars"
    )
    assert contradicted == []


def test_resolve_archives_contradicted(store, biz, detector):
    fid = store.add_fact(biz, "pricing", "widget_price", "old price")
    count = detector.resolve([fid])
    assert count == 1

    # Verify it's archived
    fact = store.get_fact(fid)
    assert fact["archived"] == 1


def test_store_integration_auto_detects(store, biz):
    """add_fact with detector wired and check_contradictions=True auto-archives."""
    # Add initial fact
    store.add_fact(biz, "pricing", "widget_price", "widget price is 10 dollars")

    # Wire up detector with mocked LLM
    detector = ContradictionDetector(store=store)
    mock_llm = MagicMock()
    mock_response = MagicMock()
    mock_response.content = "YES"
    mock_llm.chat_with_retry.return_value = mock_response
    detector._llm = mock_llm
    store.contradiction_detector = detector

    # Add contradicting fact with check enabled
    new_id = store.add_fact(
        biz, "pricing", "widget_price", "widget price is 20 dollars",
        check_contradictions=True,
    )
    assert new_id > 0

    # The old fact should be archived
    facts = store.get_facts(biz, category="pricing")
    # Only the new fact should be visible (old one archived)
    assert len(facts) == 1
    assert facts[0]["value"] == "widget price is 20 dollars"

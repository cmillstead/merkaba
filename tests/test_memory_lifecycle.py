# tests/test_memory_lifecycle.py
import json
import os
import tempfile
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from merkaba.memory.store import MemoryStore
from merkaba.memory.retrieval import MemoryRetrieval
from merkaba.memory.lifecycle import MemoryDecayJob, SessionExtractor, MemoryConsolidationJob


@pytest.fixture
def store(tmp_path):
    s = MemoryStore(db_path=str(tmp_path / "memory.db"))
    yield s
    s.close()


@pytest.fixture
def retrieval(store):
    r = MemoryRetrieval(store=store, vectors=None)
    yield r


@pytest.fixture
def mock_llm():
    return MagicMock()


# ------------------------------------------------------------------
# Schema & access tracking
# ------------------------------------------------------------------


def test_migration_adds_columns(store):
    """New lifecycle columns exist after init."""
    cursor = store._conn.execute("PRAGMA table_info(facts)")
    columns = {row[1] for row in cursor.fetchall()}
    assert "relevance_score" in columns
    assert "last_accessed" in columns
    assert "access_count" in columns
    assert "archived" in columns


def test_get_facts_excludes_archived(store):
    """Archived facts are not returned by default."""
    bid = store.add_business("Shop", "ecommerce")
    fid = store.add_fact(bid, "pricing", "avg", "4.99")
    store.archive("facts", fid)

    assert store.get_facts(bid) == []
    assert len(store.get_facts(bid, include_archived=True)) == 1


def test_archive_and_unarchive(store):
    """Round-trip archive/unarchive restores visibility."""
    bid = store.add_business("Shop", "ecommerce")
    fid = store.add_fact(bid, "pricing", "avg", "4.99")

    store.archive("facts", fid)
    assert store.get_facts(bid) == []

    store.unarchive("facts", fid)
    assert len(store.get_facts(bid)) == 1


def test_touch_accessed_updates_fields(store):
    """touch_accessed bumps access_count and sets last_accessed."""
    bid = store.add_business("Shop", "ecommerce")
    fid = store.add_fact(bid, "pricing", "avg", "4.99")

    # Initially access_count should be 0
    fact = store.get_fact(fid)
    assert fact["access_count"] == 0
    assert fact["last_accessed"] is None

    store.touch_accessed("facts", [fid])
    fact = store.get_fact(fid)
    assert fact["access_count"] == 1
    assert fact["last_accessed"] is not None

    # Touch again
    store.touch_accessed("facts", [fid])
    fact = store.get_fact(fid)
    assert fact["access_count"] == 2


def test_recall_tracks_access(retrieval):
    """recall() triggers touch_accessed for returned items."""
    store = retrieval.store
    bid = store.add_business("Shop", "ecommerce")
    fid = retrieval.remember(bid, "pricing", "avg_price", "4.99")

    # Before recall
    assert store.get_fact(fid)["access_count"] == 0

    retrieval.recall("price", business_id=bid)

    # After recall — access should be tracked
    assert store.get_fact(fid)["access_count"] == 1


def test_list_archived(store):
    """list_archived returns only archived items."""
    bid = store.add_business("Shop", "ecommerce")
    f1 = store.add_fact(bid, "pricing", "a", "1")
    f2 = store.add_fact(bid, "pricing", "b", "2")
    store.archive("facts", f1)

    archived = store.list_archived("facts")
    assert len(archived) == 1
    assert archived[0]["id"] == f1


# ------------------------------------------------------------------
# Decay job
# ------------------------------------------------------------------


def test_decay_reduces_relevance_score(store):
    """Stale items have relevance decayed."""
    bid = store.add_business("Shop", "ecommerce")
    fid = store.add_fact(bid, "pricing", "avg", "4.99")

    # Set last_accessed to long ago to make it stale
    old_time = (datetime.now() - timedelta(days=30)).isoformat()
    store._conn.execute(
        "UPDATE facts SET last_accessed = ? WHERE id = ?", (old_time, fid)
    )
    store._conn.commit()

    job = MemoryDecayJob(store=store)
    stats = job.run()

    fact = store.get_fact(fid)
    assert fact["relevance_score"] < 1.0
    assert fact["relevance_score"] == pytest.approx(0.95)
    assert stats["decayed"] >= 1


def test_decay_skips_recently_accessed(store):
    """Recently accessed items are not decayed."""
    bid = store.add_business("Shop", "ecommerce")
    fid = store.add_fact(bid, "pricing", "avg", "4.99")

    # Touch it now
    store.touch_accessed("facts", [fid])

    job = MemoryDecayJob(store=store, stale_days=7)
    job.run()

    fact = store.get_fact(fid)
    assert fact["relevance_score"] == 1.0


def test_decay_archives_below_threshold(store):
    """Items with very low relevance get archived."""
    bid = store.add_business("Shop", "ecommerce")
    fid = store.add_fact(bid, "pricing", "avg", "4.99")

    # Manually set relevance very low
    store._conn.execute(
        "UPDATE facts SET relevance_score = 0.05 WHERE id = ?", (fid,)
    )
    store._conn.commit()

    job = MemoryDecayJob(store=store, archive_threshold=0.1)
    stats = job.run()

    # Should be archived now
    assert stats["archived"] >= 1
    assert store.get_facts(bid) == []


def test_decay_returns_stats(store):
    """Decay run returns proper stats dict."""
    job = MemoryDecayJob(store=store)
    stats = job.run()
    assert "decayed" in stats
    assert "archived" in stats
    assert isinstance(stats["decayed"], int)
    assert isinstance(stats["archived"], int)


# ------------------------------------------------------------------
# Session extractor (mock LLM)
# ------------------------------------------------------------------


def test_extract_parses_llm_json(store, mock_llm):
    """Extractor parses LLM JSON response and stores facts."""
    bid = store.add_business("Shop", "ecommerce")

    mock_llm.chat.return_value = MagicMock(
        content=json.dumps([
            {"category": "pricing", "key": "avg_price", "value": "9.99", "confidence": 80},
            {"category": "inventory", "key": "stock_count", "value": "150", "confidence": 90},
        ])
    )

    extractor = SessionExtractor(llm=mock_llm, store=store)
    messages = [
        {"role": "user", "content": "What's my average price?"},
        {"role": "assistant", "content": "Your average price is $9.99 with 150 items in stock."},
    ]
    stored = extractor.extract(messages, business_id=bid)

    assert len(stored) == 2
    assert stored[0]["key"] == "avg_price"
    assert stored[1]["key"] == "stock_count"


def test_extract_skips_duplicates(store, mock_llm):
    """Existing facts are not re-added."""
    bid = store.add_business("Shop", "ecommerce")
    store.add_fact(bid, "pricing", "avg_price", "4.99")

    mock_llm.chat.return_value = MagicMock(
        content=json.dumps([
            {"category": "pricing", "key": "avg_price", "value": "9.99", "confidence": 80},
        ])
    )

    extractor = SessionExtractor(llm=mock_llm, store=store)
    stored = extractor.extract(
        [{"role": "user", "content": "test"}], business_id=bid
    )

    assert len(stored) == 0


def test_extract_handles_bad_json(store, mock_llm):
    """Malformed JSON from LLM doesn't crash."""
    bid = store.add_business("Shop", "ecommerce")
    mock_llm.chat.return_value = MagicMock(content="not valid json at all")

    extractor = SessionExtractor(llm=mock_llm, store=store)
    stored = extractor.extract(
        [{"role": "user", "content": "test"}], business_id=bid
    )

    assert stored == []


# ------------------------------------------------------------------
# Consolidation (mock LLM)
# ------------------------------------------------------------------


def test_consolidation_groups_by_category(store, mock_llm):
    """Consolidation creates summary for large groups."""
    bid = store.add_business("Shop", "ecommerce")
    for i in range(6):
        store.add_fact(bid, "pricing", f"item_{i}", f"${i}.99")

    mock_llm.chat.return_value = MagicMock(
        content="Items range from $0.99 to $5.99 in pricing."
    )

    job = MemoryConsolidationJob(store=store, llm=mock_llm, min_group_size=5)
    stats = job.run()

    assert stats["summaries"] >= 1
    assert stats["groups"] >= 1


def test_consolidation_archives_originals(store, mock_llm):
    """Original facts are archived after consolidation."""
    bid = store.add_business("Shop", "ecommerce")
    ids = []
    for i in range(6):
        ids.append(store.add_fact(bid, "pricing", f"item_{i}", f"${i}.99"))

    mock_llm.chat.return_value = MagicMock(content="Summary text.")

    job = MemoryConsolidationJob(store=store, llm=mock_llm, min_group_size=5)
    stats = job.run()

    assert stats["archived"] == 6
    # Originals should be archived
    for fid in ids:
        fact = store.get_fact(fid)
        assert fact["archived"] == 1


def test_consolidation_skips_small_groups(store, mock_llm):
    """Groups below min_group_size are not consolidated."""
    bid = store.add_business("Shop", "ecommerce")
    for i in range(3):
        store.add_fact(bid, "pricing", f"item_{i}", f"${i}.99")

    job = MemoryConsolidationJob(store=store, llm=mock_llm, min_group_size=5)
    stats = job.run()

    assert stats["groups"] == 0
    assert stats["summaries"] == 0
    assert stats["archived"] == 0
    mock_llm.chat.assert_not_called()


# ------------------------------------------------------------------
# Archive with vector cleanup
# ------------------------------------------------------------------


def test_archive_calls_vector_delete(store):
    """archive() with vectors parameter deletes the vector."""
    mock_vectors = MagicMock()
    bid = store.add_business("Shop", "ecommerce")
    fid = store.add_fact(bid, "pricing", "avg", "4.99")

    store.archive("facts", fid, vectors=mock_vectors)

    mock_vectors.delete_vectors.assert_called_once_with("facts", [str(fid)])
    assert store.get_facts(bid) == []


def test_archive_without_vectors_still_works(store):
    """archive() without vectors parameter works as before."""
    bid = store.add_business("Shop", "ecommerce")
    fid = store.add_fact(bid, "pricing", "avg", "4.99")

    store.archive("facts", fid)
    assert store.get_facts(bid) == []


# ------------------------------------------------------------------
# Post-consolidation vector rebuild
# ------------------------------------------------------------------


def test_consolidation_triggers_vector_rebuild(store, mock_llm):
    """Consolidation with vectors triggers rebuild_from_store after archiving."""
    mock_vectors = MagicMock()
    mock_vectors.rebuild_from_store.return_value = {"facts": 1, "decisions": 0, "learnings": 0}

    bid = store.add_business("Shop", "ecommerce")
    for i in range(6):
        store.add_fact(bid, "pricing", f"item_{i}", f"${i}.99")

    mock_llm.chat.return_value = MagicMock(content="Summary text.")

    job = MemoryConsolidationJob(store=store, llm=mock_llm, vectors=mock_vectors)
    stats = job.run()

    mock_vectors.rebuild_from_store.assert_called_once_with(store)
    assert stats["summaries"] >= 1


def test_consolidation_without_vectors_still_works(store, mock_llm):
    """Consolidation without vectors parameter works as before."""
    bid = store.add_business("Shop", "ecommerce")
    for i in range(6):
        store.add_fact(bid, "pricing", f"item_{i}", f"${i}.99")

    mock_llm.chat.return_value = MagicMock(content="Summary text.")

    job = MemoryConsolidationJob(store=store, llm=mock_llm)
    stats = job.run()
    assert stats["summaries"] >= 1


# ------------------------------------------------------------------
# Relationship extraction
# ------------------------------------------------------------------


def test_extract_produces_relationships(store, mock_llm):
    """Extractor parses relationships from LLM response."""
    bid = store.add_business("Corp", "enterprise")

    mock_llm.chat.return_value = MagicMock(
        content=json.dumps({
            "facts": [
                {"category": "org", "key": "ceo", "value": "Alice", "confidence": 90},
            ],
            "relationships": [
                {
                    "entity": "Alice",
                    "entity_type": "person",
                    "relation": "manages",
                    "related_entity": "engineering",
                    "related_type": "team",
                },
            ],
        })
    )

    extractor = SessionExtractor(llm=mock_llm, store=store)
    stored = extractor.extract(
        [{"role": "user", "content": "Alice manages engineering"}],
        business_id=bid,
    )

    assert len(stored) >= 1

    rels = store.get_relationships(bid)
    assert len(rels) == 1
    assert rels[0]["entity_id"] == "Alice"
    assert rels[0]["relation"] == "manages"
    assert rels[0]["related_entity"] == "engineering"


def test_extract_deduplicates_relationships(store, mock_llm):
    """Existing relationships are not re-added."""
    bid = store.add_business("Corp", "enterprise")
    store.add_relationship(bid, "person", "Alice", "manages", "engineering")

    mock_llm.chat.return_value = MagicMock(
        content=json.dumps({
            "facts": [],
            "relationships": [
                {
                    "entity": "Alice",
                    "entity_type": "person",
                    "relation": "manages",
                    "related_entity": "engineering",
                    "related_type": "team",
                },
            ],
        })
    )

    extractor = SessionExtractor(llm=mock_llm, store=store)
    extractor.extract(
        [{"role": "user", "content": "Alice manages engineering"}],
        business_id=bid,
    )

    rels = store.get_relationships(bid)
    assert len(rels) == 1


def test_extract_backward_compat_array_format(store, mock_llm):
    """Extractor still handles old array-of-facts format."""
    bid = store.add_business("Shop", "ecommerce")

    mock_llm.chat.return_value = MagicMock(
        content=json.dumps([
            {"category": "pricing", "key": "avg", "value": "4.99", "confidence": 80},
        ])
    )

    extractor = SessionExtractor(llm=mock_llm, store=store)
    stored = extractor.extract(
        [{"role": "user", "content": "test"}],
        business_id=bid,
    )
    assert len(stored) == 1

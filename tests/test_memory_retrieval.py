# tests/test_memory_retrieval.py
import tempfile
import os
import pytest
from unittest.mock import MagicMock, patch
from merkaba.memory.store import MemoryStore
from merkaba.memory.retrieval import MemoryRetrieval, RetrievalConfig


@pytest.fixture
def retrieval():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "memory.db")
        store = MemoryStore(db_path=db_path)
        r = MemoryRetrieval(store=store, vectors=None)
        yield r
        r.close()


# ------------------------------------------------------------------
# Existing tests (7)
# ------------------------------------------------------------------

def test_remember_stores_fact(retrieval):
    biz_id = retrieval.store.add_business("Shop", "ecommerce")
    fact_id = retrieval.remember(biz_id, "pricing", "avg_price", "4.99")
    assert fact_id == 1
    fact = retrieval.store.get_fact(fact_id)
    assert fact["value"] == "4.99"


def test_recall_keyword_search(retrieval):
    biz_id = retrieval.store.add_business("Shop", "ecommerce")
    retrieval.remember(biz_id, "pricing", "avg_price", "4.99")
    retrieval.remember(biz_id, "pricing", "max_price", "12.99")
    retrieval.remember(biz_id, "inventory", "total", "50")

    results = retrieval.recall("price", business_id=biz_id)
    assert len(results) == 2
    assert all(r["type"] == "fact" for r in results)


def test_recall_returns_decisions(retrieval):
    biz_id = retrieval.store.add_business("Shop", "ecommerce")
    retrieval.store.add_decision(
        biz_id, "pricing", "Lower price to $3.99", "Competitors are cheaper"
    )
    results = retrieval.recall("price", business_id=biz_id)
    assert len(results) == 1
    assert results[0]["type"] == "decision"


def test_recall_returns_learnings(retrieval):
    retrieval.store.add_learning("marketing", "Post at 9am for engagement")
    results = retrieval.recall("9am")
    assert len(results) == 1
    assert results[0]["type"] == "learning"


def test_what_do_i_know_with_results(retrieval):
    biz_id = retrieval.store.add_business("Shop", "ecommerce")
    retrieval.remember(biz_id, "pricing", "avg_price", "4.99")
    summary = retrieval.what_do_i_know("price", business_id=biz_id)
    assert "4.99" in summary
    assert "pricing" in summary.lower()


def test_what_do_i_know_empty(retrieval):
    summary = retrieval.what_do_i_know("nonexistent topic")
    assert "don't have any information" in summary


def test_recall_respects_limit(retrieval):
    biz_id = retrieval.store.add_business("Shop", "ecommerce")
    for i in range(10):
        retrieval.remember(biz_id, "pricing", f"price_{i}", str(i))

    results = retrieval.recall("price", business_id=biz_id, limit=3)
    assert len(results) == 3


# ------------------------------------------------------------------
# New tests: keyword scoring
# ------------------------------------------------------------------

def test_keyword_score_values(retrieval):
    """Full, partial, and no match scoring."""
    # Full match: all query words present
    score = retrieval._keyword_score(["hello", "world"], "hello world foo")
    assert score == 1.0

    # Partial match: 1 of 2 words
    score = retrieval._keyword_score(["hello", "world"], "hello foo bar")
    assert score == 0.5

    # No match
    score = retrieval._keyword_score(["hello", "world"], "foo bar baz")
    assert score == 0.0

    # Empty query words
    score = retrieval._keyword_score([], "anything")
    assert score == 0.0


def test_relevance_threshold_filters(retrieval):
    """Below-threshold items are excluded from results."""
    biz_id = retrieval.store.add_business("Shop", "ecommerce")
    # "inventory total 50" — query "price" won't match any word
    retrieval.remember(biz_id, "inventory", "total", "50")
    # "pricing avg_price 4.99" — query "price" matches "pricing" and "avg_price"
    retrieval.remember(biz_id, "pricing", "avg_price", "4.99")

    results = retrieval.recall("price", business_id=biz_id)
    # "inventory total 50" should be filtered out (score 0.0 < 0.25)
    assert all("pricing" in r.get("category", "") or "price" in r.get("key", "") for r in results)
    # The pricing fact should be present
    assert len(results) >= 1


def test_results_sorted_by_score(retrieval):
    """Higher-scoring results come first."""
    biz_id = retrieval.store.add_business("Shop", "ecommerce")
    # 2-word query: "average price"
    # fact 1: "pricing avg_price 4.99" — matches "price" (in avg_price) = 1/2
    retrieval.remember(biz_id, "pricing", "avg_price", "4.99")
    # fact 2: "pricing average_price 9.99" — matches "average" (in average_price) and "price" = 2/2
    retrieval.remember(biz_id, "pricing", "average_price", "9.99")

    results = retrieval.recall("average price", business_id=biz_id)
    assert len(results) >= 2
    # The result matching both words should be first
    assert results[0]["score"] >= results[1]["score"]


def test_token_budget_trims(retrieval):
    """Token budget forces trim from tail."""
    biz_id = retrieval.store.add_business("Shop", "ecommerce")
    # Create many facts that exceed a tiny budget
    for i in range(20):
        retrieval.remember(biz_id, "data", f"item_{i}", "x" * 200)

    # Use a tiny budget: 50 tokens = ~200 chars — should trim heavily
    retrieval.config = RetrievalConfig(
        max_items=20, min_relevance_score=0.0, max_context_tokens=50
    )
    results = retrieval.recall("item", business_id=biz_id)
    # With ~200 chars per result and 200 char budget, should get very few
    assert len(results) < 20
    assert len(results) >= 1  # at least first item always included


def test_business_scoping(retrieval):
    """business_id=2 excludes business_id=1 facts."""
    biz1 = retrieval.store.add_business("Shop1", "ecommerce")
    biz2 = retrieval.store.add_business("Shop2", "ecommerce")
    retrieval.remember(biz1, "pricing", "price", "1.99")
    retrieval.remember(biz2, "pricing", "price", "9.99")

    # Query scoped to biz2
    results = retrieval.recall("price", business_id=biz2)
    assert len(results) == 1
    assert results[0]["value"] == "9.99"

    # Query scoped to biz1
    results = retrieval.recall("price", business_id=biz1)
    assert len(results) == 1
    assert results[0]["value"] == "1.99"


def test_custom_retrieval_config(retrieval):
    """Custom max_items is respected."""
    biz_id = retrieval.store.add_business("Shop", "ecommerce")
    for i in range(10):
        retrieval.remember(biz_id, "pricing", f"price_{i}", str(i))

    retrieval.config = RetrievalConfig(max_items=2, min_relevance_score=0.0)
    # Call without explicit limit — should use config.max_items
    results = retrieval.recall("price", business_id=biz_id)
    assert len(results) == 2


# ------------------------------------------------------------------
# Semantic recall tests (mock VectorMemory)
# ------------------------------------------------------------------

@pytest.fixture
def semantic_retrieval():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "memory.db")
        store = MemoryStore(db_path=db_path)
        mock_vectors = MagicMock()
        mock_vectors.search_facts.return_value = []
        mock_vectors.search_decisions.return_value = []
        mock_vectors.search_learnings.return_value = []
        r = MemoryRetrieval(store=store, vectors=mock_vectors)
        yield r
        r.close()


def test_semantic_fact_search(semantic_retrieval):
    """Semantic fact search hydrates facts from store by vector hit IDs."""
    r = semantic_retrieval
    biz_id = r.store.add_business("Shop", "ecommerce")
    fact_id = r.store.add_fact(biz_id, "pricing", "avg_price", "4.99")

    r.vectors.search_facts.return_value = [{"id": fact_id, "distance": 0.5}]
    results = r.recall("price", business_id=biz_id)

    fact_results = [x for x in results if x["type"] == "fact"]
    assert len(fact_results) == 1
    assert fact_results[0]["value"] == "4.99"
    assert fact_results[0]["key"] == "avg_price"
    assert fact_results[0]["distance"] == 0.5
    r.vectors.search_facts.assert_called_once_with("price", biz_id, 5)


def test_semantic_decision_search(semantic_retrieval):
    """Semantic decision search hydrates decisions from store."""
    r = semantic_retrieval
    biz_id = r.store.add_business("Shop", "ecommerce")
    dec_id = r.store.add_decision(
        biz_id, "pricing", "Lower price to $3.99", "Competitors are cheaper"
    )

    r.vectors.search_decisions.return_value = [{"id": dec_id, "distance": 0.3}]
    results = r.recall("price", business_id=biz_id)

    dec_results = [x for x in results if x["type"] == "decision"]
    assert len(dec_results) == 1
    assert dec_results[0]["decision"] == "Lower price to $3.99"
    assert dec_results[0]["reasoning"] == "Competitors are cheaper"
    assert dec_results[0]["distance"] == 0.3


def test_semantic_learning_search(semantic_retrieval):
    """Semantic learning search hydrates learnings from store."""
    r = semantic_retrieval
    learn_id = r.store.add_learning("marketing", "Post at 9am for engagement")

    r.vectors.search_learnings.return_value = [{"id": learn_id, "distance": 0.7}]
    results = r.recall("engagement")

    learn_results = [x for x in results if x["type"] == "learning"]
    assert len(learn_results) == 1
    assert learn_results[0]["insight"] == "Post at 9am for engagement"
    assert learn_results[0]["distance"] == 0.7


def test_semantic_distance_threshold_filtering(semantic_retrieval):
    """Hits with distance > max_distance are excluded from semantic results;
    keyword backfill may recover them as a safety net."""
    r = semantic_retrieval
    biz_id = r.store.add_business("Shop", "ecommerce")
    close_id = r.store.add_fact(biz_id, "pricing", "close_price", "1.99")
    far_id = r.store.add_fact(biz_id, "pricing", "far_price", "99.99")

    # max_distance defaults to 1.5 -- one hit within, one outside
    r.vectors.search_facts.return_value = [
        {"id": close_id, "distance": 0.5},
        {"id": far_id, "distance": 2.0},
    ]
    results = r.recall("price", business_id=biz_id)

    fact_results = [x for x in results if x["type"] == "fact"]
    # Close hit always present; far hit excluded by semantic but may be
    # recovered by keyword backfill (both contain "price" in key)
    assert any(f["value"] == "1.99" for f in fact_results)
    # The close semantic hit should appear first (higher score)
    assert fact_results[0]["value"] == "1.99"


def test_semantic_score_calculation(semantic_retrieval):
    """Score = 1 - distance/max_distance, clamped at 0."""
    r = semantic_retrieval
    biz_id = r.store.add_business("Shop", "ecommerce")
    f1 = r.store.add_fact(biz_id, "a", "k1", "v1")
    f2 = r.store.add_fact(biz_id, "a", "k2", "v2")
    f3 = r.store.add_fact(biz_id, "a", "k3", "v3")

    # max_distance = 1.5
    r.vectors.search_facts.return_value = [
        {"id": f1, "distance": 0.0},    # score = 1.0
        {"id": f2, "distance": 0.75},   # score = 0.5
        {"id": f3, "distance": 1.5},    # score = 0.0
    ]
    results = r.recall("test", business_id=biz_id)

    fact_results = [x for x in results if x["type"] == "fact"]
    assert len(fact_results) == 3
    scores = {x["key"]: x["score"] for x in fact_results}
    assert scores["k1"] == pytest.approx(1.0)
    assert scores["k2"] == pytest.approx(0.5)
    assert scores["k3"] == pytest.approx(0.0)


def test_semantic_results_sorted_by_distance(semantic_retrieval):
    """Results are sorted by distance ascending (closest first)."""
    r = semantic_retrieval
    biz_id = r.store.add_business("Shop", "ecommerce")
    f1 = r.store.add_fact(biz_id, "a", "far", "v1")
    f2 = r.store.add_fact(biz_id, "a", "close", "v2")
    f3 = r.store.add_fact(biz_id, "a", "mid", "v3")

    r.vectors.search_facts.return_value = [
        {"id": f1, "distance": 1.2},
        {"id": f2, "distance": 0.1},
        {"id": f3, "distance": 0.6},
    ]
    results = r.recall("test", business_id=biz_id)

    fact_results = [x for x in results if x["type"] == "fact"]
    distances = [x["distance"] for x in fact_results]
    assert distances == sorted(distances), "Results should be sorted by distance ascending"
    assert fact_results[0]["key"] == "close"
    assert fact_results[1]["key"] == "mid"
    assert fact_results[2]["key"] == "far"


def test_semantic_recall_no_hits(semantic_retrieval):
    """Empty vector results yield empty semantic list."""
    r = semantic_retrieval
    # All mock return values are already [], so no need to set them
    results = r.recall("anything")
    # Only episodes (if any) should appear -- no facts/decisions/learnings
    semantic_results = [
        x for x in results if x["type"] in ("fact", "decision", "learning")
    ]
    assert semantic_results == []


def test_semantic_mixed_with_episodes(semantic_retrieval):
    """Semantic results are combined with recent episodes."""
    r = semantic_retrieval
    biz_id = r.store.add_business("Shop", "ecommerce")
    fact_id = r.store.add_fact(biz_id, "pricing", "price", "4.99")

    # Add an episode via the store
    r.store.add_episode(
        business_id=biz_id,
        task_type="pricing_check",
        task_id=1,
        summary="Checked competitor prices",
        outcome="success",
    )

    r.vectors.search_facts.return_value = [{"id": fact_id, "distance": 0.5}]
    results = r.recall("price", business_id=biz_id)

    types_present = {x["type"] for x in results}
    assert "fact" in types_present
    assert "episode" in types_present


def test_semantic_access_tracking(semantic_retrieval):
    """touch_accessed is called for facts returned from semantic recall."""
    r = semantic_retrieval
    biz_id = r.store.add_business("Shop", "ecommerce")
    fact_id = r.store.add_fact(biz_id, "pricing", "price", "4.99")

    r.vectors.search_facts.return_value = [{"id": fact_id, "distance": 0.5}]
    r.recall("price", business_id=biz_id)

    # Verify access_count was incremented
    fact = r.store.get_fact(fact_id)
    assert fact["access_count"] >= 1
    assert fact["last_accessed"] is not None


def test_remember_with_vectors_indexes_fact(semantic_retrieval):
    """When vectors is present, remember() calls vectors.index_fact()."""
    r = semantic_retrieval
    biz_id = r.store.add_business("Shop", "ecommerce")
    fact_id = r.remember(biz_id, "pricing", "avg_price", "4.99")

    r.vectors.index_fact.assert_called_once_with(
        fact_id, biz_id, "pricing: avg_price = 4.99"
    )


def test_keyword_backfill_when_vectors_miss(semantic_retrieval):
    """Facts only in SQLite (not indexed in vectors) are found via keyword backfill."""
    r = semantic_retrieval
    biz_id = r.store.add_business("Research", "research")
    # Add facts directly to SQLite (simulating seed script without vector indexing)
    f1 = r.store.add_fact(biz_id, "overview", "Bittensor protocol", "Decentralized AI with subnets")
    f2 = r.store.add_fact(biz_id, "sn59", "Agent Arena", "Deploy agents on Twitter")

    # Vectors return nothing — facts were never indexed there
    r.vectors.search_facts.return_value = []
    r.vectors.search_decisions.return_value = []
    r.vectors.search_learnings.return_value = []

    results = r.recall("Bittensor subnet", business_id=biz_id)
    fact_results = [x for x in results if x["type"] == "fact"]
    assert len(fact_results) >= 1
    keys = {f["key"] for f in fact_results}
    assert "Bittensor protocol" in keys


def test_keyword_backfill_deduplicates(semantic_retrieval):
    """Keyword backfill does not duplicate facts already found by vectors."""
    r = semantic_retrieval
    biz_id = r.store.add_business("Shop", "ecommerce")
    f1 = r.store.add_fact(biz_id, "pricing", "widget_price", "9.99")

    # Vectors find it
    r.vectors.search_facts.return_value = [{"id": f1, "distance": 0.3}]
    r.vectors.search_decisions.return_value = []
    r.vectors.search_learnings.return_value = []

    results = r.recall("widget price", business_id=biz_id)
    fact_results = [x for x in results if x["type"] == "fact"]
    # Should appear exactly once, not duplicated by keyword backfill
    assert len(fact_results) == 1
    assert fact_results[0]["value"] == "9.99"


# ------------------------------------------------------------------
# Relationship recall tests
# ------------------------------------------------------------------


def test_recall_includes_relationships(retrieval):
    """recall() returns relationship results when entities match."""
    store = retrieval.store
    bid = store.add_business("Corp", "enterprise")
    store.add_relationship(bid, "person", "Alice", "manages", "auth team")

    results = retrieval.recall("Alice", business_id=bid)
    rel_results = [r for r in results if r["type"] == "relationship"]
    assert len(rel_results) >= 1
    assert rel_results[0]["entity_id"] == "Alice"
    assert rel_results[0]["related_entity"] == "auth team"


def test_recall_relationship_multi_hop(retrieval):
    """recall() traverses relationships to find connected entities."""
    store = retrieval.store
    bid = store.add_business("Corp", "enterprise")
    store.add_relationship(bid, "person", "Alice", "manages", "auth team")
    store.add_relationship(bid, "team", "auth team", "handles", "permissions")

    results = retrieval.recall("Alice permissions", business_id=bid)
    rel_results = [r for r in results if r["type"] == "relationship"]
    related = {r["related_entity"] for r in rel_results}
    assert "auth team" in related
    assert "permissions" in related


def test_recall_no_relationship_noise(retrieval):
    """recall() does not return relationships when no entities match."""
    store = retrieval.store
    bid = store.add_business("Corp", "enterprise")
    store.add_relationship(bid, "person", "Alice", "manages", "auth team")
    retrieval.remember(bid, "pricing", "avg", "4.99")

    results = retrieval.recall("price", business_id=bid)
    rel_results = [r for r in results if r["type"] == "relationship"]
    assert len(rel_results) == 0

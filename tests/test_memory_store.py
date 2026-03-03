# tests/test_memory_store.py
import tempfile
import os
import pytest
from merkaba.memory.store import MemoryStore


@pytest.fixture
def store():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "memory.db")
        s = MemoryStore(db_path=db_path)
        yield s
        s.close()


# --- Business CRUD ---


def test_add_business(store):
    biz_id = store.add_business("Test Shop", "ecommerce")
    assert biz_id == 1


def test_get_business(store):
    biz_id = store.add_business("Test Shop", "ecommerce", autonomy_level=2)
    biz = store.get_business(biz_id)
    assert biz["name"] == "Test Shop"
    assert biz["type"] == "ecommerce"
    assert biz["autonomy_level"] == 2


def test_get_business_not_found(store):
    assert store.get_business(999) is None


def test_list_businesses(store):
    store.add_business("Shop A", "ecommerce")
    store.add_business("Blog B", "content")
    businesses = store.list_businesses()
    assert len(businesses) == 2
    assert businesses[0]["name"] == "Shop A"


def test_update_business(store):
    biz_id = store.add_business("Old Name", "ecommerce")
    store.update_business(biz_id, name="New Name", autonomy_level=3)
    biz = store.get_business(biz_id)
    assert biz["name"] == "New Name"
    assert biz["autonomy_level"] == 3


# --- Facts CRUD ---


def test_add_and_get_fact(store):
    biz_id = store.add_business("Shop", "ecommerce")
    fact_id = store.add_fact(biz_id, "pricing", "avg_price", "4.99")
    fact = store.get_fact(fact_id)
    assert fact["category"] == "pricing"
    assert fact["key"] == "avg_price"
    assert fact["value"] == "4.99"
    assert fact["confidence"] == 100


def test_get_facts_by_category(store):
    biz_id = store.add_business("Shop", "ecommerce")
    store.add_fact(biz_id, "pricing", "avg_price", "4.99")
    store.add_fact(biz_id, "pricing", "max_price", "12.99")
    store.add_fact(biz_id, "inventory", "total_items", "50")

    pricing_facts = store.get_facts(biz_id, category="pricing")
    assert len(pricing_facts) == 2

    all_facts = store.get_facts(biz_id)
    assert len(all_facts) == 3


def test_update_fact(store):
    biz_id = store.add_business("Shop", "ecommerce")
    fact_id = store.add_fact(biz_id, "pricing", "avg_price", "4.99")
    store.update_fact(fact_id, value="5.99", confidence=90)
    fact = store.get_fact(fact_id)
    assert fact["value"] == "5.99"
    assert fact["confidence"] == 90


# --- Decisions CRUD ---


def test_add_decision(store):
    biz_id = store.add_business("Shop", "ecommerce")
    dec_id = store.add_decision(
        biz_id, "pricing", "Lower price to $3.99", "Competitors are cheaper"
    )
    decisions = store.get_decisions(biz_id)
    assert len(decisions) == 1
    assert decisions[0]["decision"] == "Lower price to $3.99"


def test_get_decision_by_id(store):
    """get_decision retrieves a single decision by ID."""
    biz_id = store.add_business("Shop", "ecommerce")
    dec_id = store.add_decision(
        biz_id, "pricing", "Lower price to $3.99", "Competitors are cheaper"
    )
    d = store.get_decision(dec_id)
    assert d is not None
    assert d["id"] == dec_id
    assert d["business_id"] == biz_id
    assert d["action_type"] == "pricing"
    assert d["decision"] == "Lower price to $3.99"
    assert d["reasoning"] == "Competitors are cheaper"
    assert d["created_at"] is not None


def test_get_decision_not_found(store):
    """get_decision returns None for a non-existent ID."""
    assert store.get_decision(999) is None


def test_get_decisions_by_type(store):
    biz_id = store.add_business("Shop", "ecommerce")
    store.add_decision(biz_id, "pricing", "Lower price", "Competition")
    store.add_decision(biz_id, "inventory", "Restock", "Low stock")

    pricing = store.get_decisions(biz_id, action_type="pricing")
    assert len(pricing) == 1

    all_decisions = store.get_decisions(biz_id)
    assert len(all_decisions) == 2


def test_update_decision_outcome(store):
    biz_id = store.add_business("Shop", "ecommerce")
    dec_id = store.add_decision(biz_id, "pricing", "Lower price", "Competition")
    store.update_decision_outcome(dec_id, "Sales increased 20%")
    decisions = store.get_decisions(biz_id)
    assert decisions[0]["outcome"] == "Sales increased 20%"


# --- Relationships CRUD ---


def test_add_relationship(store):
    biz_id = store.add_business("Shop", "ecommerce")
    rel_id = store.add_relationship(
        biz_id, "product", "SKU-001", "competes_with", "SKU-002",
        metadata={"strength": "direct"},
    )
    rels = store.get_relationships(biz_id)
    assert len(rels) == 1
    assert rels[0]["metadata"] == {"strength": "direct"}


def test_get_relationships_by_type(store):
    biz_id = store.add_business("Shop", "ecommerce")
    store.add_relationship(biz_id, "product", "SKU-001", "competes_with", "SKU-002")
    store.add_relationship(biz_id, "customer", "C-001", "purchased", "SKU-001")

    products = store.get_relationships(biz_id, entity_type="product")
    assert len(products) == 1

    all_rels = store.get_relationships(biz_id)
    assert len(all_rels) == 2


# --- State CRUD ---


def test_set_and_get_state(store):
    biz_id = store.add_business("Shop", "ecommerce")
    store.set_state(biz_id, "listing", "L-001", "status", "active")
    states = store.get_state(biz_id, entity_type="listing", entity_id="L-001")
    assert len(states) == 1
    assert states[0]["value"] == "active"


def test_state_upsert(store):
    biz_id = store.add_business("Shop", "ecommerce")
    store.set_state(biz_id, "listing", "L-001", "status", "draft")
    store.set_state(biz_id, "listing", "L-001", "status", "active")
    states = store.get_state(biz_id, entity_type="listing", entity_id="L-001")
    assert len(states) == 1
    assert states[0]["value"] == "active"


def test_get_state_filters(store):
    biz_id = store.add_business("Shop", "ecommerce")
    store.set_state(biz_id, "listing", "L-001", "status", "active")
    store.set_state(biz_id, "listing", "L-002", "status", "draft")
    store.set_state(biz_id, "order", "O-001", "status", "shipped")

    listings = store.get_state(biz_id, entity_type="listing")
    assert len(listings) == 2

    all_state = store.get_state(biz_id)
    assert len(all_state) == 3


# --- Learnings CRUD ---


def test_add_learning(store):
    biz_id = store.add_business("Shop", "ecommerce")
    learn_id = store.add_learning(
        "pricing", "Lower prices increase volume but not revenue",
        evidence="A/B test results",
        confidence=80,
        source_business_id=biz_id,
    )
    learnings = store.get_learnings()
    assert len(learnings) == 1
    assert learnings[0]["insight"] == "Lower prices increase volume but not revenue"


def test_get_learning_by_id(store):
    """get_learning retrieves a single learning by ID."""
    biz_id = store.add_business("Shop", "ecommerce")
    learn_id = store.add_learning(
        "pricing", "Lower prices increase volume but not revenue",
        evidence="A/B test results",
        confidence=80,
        source_business_id=biz_id,
    )
    l = store.get_learning(learn_id)
    assert l is not None
    assert l["id"] == learn_id
    assert l["source_business_id"] == biz_id
    assert l["category"] == "pricing"
    assert l["insight"] == "Lower prices increase volume but not revenue"
    assert l["evidence"] == "A/B test results"
    assert l["confidence"] == 80
    assert l["created_at"] is not None


def test_get_learning_not_found(store):
    """get_learning returns None for a non-existent ID."""
    assert store.get_learning(999) is None


def test_get_learnings_by_category(store):
    store.add_learning("pricing", "Insight 1")
    store.add_learning("marketing", "Insight 2")
    store.add_learning("pricing", "Insight 3")

    pricing = store.get_learnings(category="pricing")
    assert len(pricing) == 2

    all_learnings = store.get_learnings()
    assert len(all_learnings) == 3


# --- Stats ---


def test_stats(store):
    biz_id = store.add_business("Shop", "ecommerce")
    store.add_fact(biz_id, "pricing", "avg_price", "4.99")
    store.add_learning("pricing", "Test insight")

    stats = store.stats()
    assert stats["businesses"] == 1
    assert stats["facts"] == 1
    assert stats["learnings"] == 1
    assert stats["decisions"] == 0


# --- Database Indexes ---


def test_database_indexes_exist(store):
    """All expected indexes are created during table initialization."""
    expected_indexes = {
        "idx_episodes_business_type",
        "idx_facts_business_archived",
        "idx_decisions_business_archived",
        "idx_learnings_archived",
        "idx_relationships_entity",
        "idx_relationships_related",
        "idx_state_business_type",
    }
    tables_with_indexes = [
        "episodes", "facts", "decisions", "learnings",
        "relationships", "state",
    ]
    found_indexes = set()
    cursor = store._conn.cursor()
    for table in tables_with_indexes:
        cursor.execute(f"PRAGMA index_list({table})")
        for row in cursor.fetchall():
            found_indexes.add(row[1])  # column 1 is the index name

    missing = expected_indexes - found_indexes
    assert not missing, f"Missing indexes: {missing}"


# --- Episodes CRUD ---


def test_add_episode_basic(store):
    """add_episode creates an episode and returns a valid integer ID."""
    biz_id = store.add_business("Shop", "ecommerce")
    ep_id = store.add_episode(
        biz_id, "listing", 1, "Created a listing", "success"
    )
    assert isinstance(ep_id, int)
    assert ep_id >= 1


def test_get_episode_by_id(store):
    """get_episode retrieves an episode with all fields correctly populated."""
    biz_id = store.add_business("Shop", "ecommerce")
    ep_id = store.add_episode(
        biz_id,
        "pricing",
        42,
        "Adjusted prices",
        "success",
        outcome_details="Lowered by 10%",
        key_decisions=["reduce margin", "keep volume"],
        duration_seconds=120,
        tags=["pricing", "experiment"],
    )
    ep = store.get_episode(ep_id)
    assert ep is not None
    assert ep["id"] == ep_id
    assert ep["business_id"] == biz_id
    assert ep["task_type"] == "pricing"
    assert ep["task_id"] == 42
    assert ep["summary"] == "Adjusted prices"
    assert ep["outcome"] == "success"
    assert ep["outcome_details"] == "Lowered by 10%"
    assert ep["key_decisions"] == ["reduce margin", "keep volume"]
    assert ep["duration_seconds"] == 120
    assert ep["tags"] == ["pricing", "experiment"]
    assert ep["created_at"] is not None


def test_get_episode_not_found(store):
    """get_episode returns None for a non-existent ID."""
    assert store.get_episode(999) is None


def test_get_episodes_filtered_by_business_id(store):
    """get_episodes returns only episodes for the specified business."""
    biz_a = store.add_business("Shop A", "ecommerce")
    biz_b = store.add_business("Shop B", "ecommerce")
    store.add_episode(biz_a, "listing", 1, "Task A1", "success")
    store.add_episode(biz_a, "listing", 2, "Task A2", "success")
    store.add_episode(biz_b, "listing", 3, "Task B1", "failure")

    eps_a = store.get_episodes(business_id=biz_a)
    assert len(eps_a) == 2
    assert all(ep["business_id"] == biz_a for ep in eps_a)

    eps_b = store.get_episodes(business_id=biz_b)
    assert len(eps_b) == 1
    assert eps_b[0]["summary"] == "Task B1"


def test_get_episodes_filtered_by_task_type(store):
    """get_episodes returns only episodes matching the specified task_type."""
    biz_id = store.add_business("Shop", "ecommerce")
    store.add_episode(biz_id, "listing", 1, "Listing work", "success")
    store.add_episode(biz_id, "pricing", 2, "Pricing work", "success")
    store.add_episode(biz_id, "listing", 3, "More listing", "failure")

    listings = store.get_episodes(task_type="listing")
    assert len(listings) == 2
    assert all(ep["task_type"] == "listing" for ep in listings)

    pricing = store.get_episodes(task_type="pricing")
    assert len(pricing) == 1
    assert pricing[0]["task_type"] == "pricing"


def test_get_episodes_limit(store):
    """get_episodes respects the limit parameter."""
    biz_id = store.add_business("Shop", "ecommerce")
    for i in range(5):
        store.add_episode(biz_id, "listing", i, f"Task {i}", "success")

    eps = store.get_episodes(limit=3)
    assert len(eps) == 3

    eps_all = store.get_episodes(limit=10)
    assert len(eps_all) == 5


def test_get_episodes_ordering(store):
    """get_episodes returns most recent episodes first (ORDER BY created_at DESC)."""
    import time

    biz_id = store.add_business("Shop", "ecommerce")
    store.add_episode(biz_id, "listing", 1, "First", "success")
    time.sleep(0.05)
    store.add_episode(biz_id, "listing", 2, "Second", "success")
    time.sleep(0.05)
    store.add_episode(biz_id, "listing", 3, "Third", "success")

    eps = store.get_episodes()
    assert eps[0]["summary"] == "Third"
    assert eps[1]["summary"] == "Second"
    assert eps[2]["summary"] == "First"


def test_key_decisions_json_roundtrip(store):
    """key_decisions stored as JSON is parsed back to a list on retrieval."""
    biz_id = store.add_business("Shop", "ecommerce")
    decisions = ["use lower price", "bundle products", "free shipping"]
    ep_id = store.add_episode(
        biz_id, "pricing", 1, "Pricing run", "success",
        key_decisions=decisions,
    )
    ep = store.get_episode(ep_id)
    assert ep["key_decisions"] == decisions
    assert isinstance(ep["key_decisions"], list)


def test_tags_json_roundtrip(store):
    """tags stored as JSON is parsed back to a list on retrieval."""
    biz_id = store.add_business("Shop", "ecommerce")
    tags = ["urgent", "pricing", "q1-2026"]
    ep_id = store.add_episode(
        biz_id, "pricing", 1, "Tagged task", "success",
        tags=tags,
    )
    ep = store.get_episode(ep_id)
    assert ep["tags"] == tags
    assert isinstance(ep["tags"], list)


def test_key_decisions_none(store):
    """When key_decisions is None, it is retrieved as None (not parsed)."""
    biz_id = store.add_business("Shop", "ecommerce")
    ep_id = store.add_episode(
        biz_id, "listing", 1, "No decisions", "success",
        key_decisions=None,
    )
    ep = store.get_episode(ep_id)
    assert ep["key_decisions"] is None


def test_parse_episode_json_malformed(store):
    """When key_decisions/tags contain invalid JSON, _parse_episode_json falls back to empty list."""
    malformed = {
        "key_decisions": "{not valid json",
        "tags": "[also broken",
    }
    result = store._parse_episode_json(malformed)
    assert result["key_decisions"] == []
    assert result["tags"] == []


# --- Traversal ---


def test_traverse_single_hop(store):
    """traverse returns direct relationships."""
    bid = store.add_business("Corp", "enterprise")
    store.add_relationship(bid, "person", "Alice", "manages", "auth team")
    store.add_relationship(bid, "person", "Bob", "manages", "billing team")

    results = store.traverse("Alice", depth=1, business_id=bid)
    assert len(results) == 1
    assert results[0]["related_entity"] == "auth team"


def test_traverse_multi_hop(store):
    """traverse follows edges up to depth."""
    bid = store.add_business("Corp", "enterprise")
    store.add_relationship(bid, "person", "Alice", "manages", "auth team")
    store.add_relationship(bid, "team", "auth team", "handles", "permissions")

    results = store.traverse("Alice", depth=2, business_id=bid)
    entities = {r["related_entity"] for r in results}
    assert "auth team" in entities
    assert "permissions" in entities


def test_traverse_bidirectional(store):
    """traverse follows edges in both directions."""
    bid = store.add_business("Corp", "enterprise")
    store.add_relationship(bid, "person", "Alice", "manages", "auth team")

    results = store.traverse("auth team", depth=1, business_id=bid)
    assert len(results) >= 1
    entity_ids = {r["entity_id"] for r in results}
    assert "Alice" in entity_ids


def test_traverse_respects_depth_limit(store):
    """traverse stops at depth limit."""
    bid = store.add_business("Corp", "enterprise")
    store.add_relationship(bid, "a", "A", "links", "B")
    store.add_relationship(bid, "b", "B", "links", "C")
    store.add_relationship(bid, "c", "C", "links", "D")

    results = store.traverse("A", depth=1, business_id=bid)
    entities = {r["related_entity"] for r in results}
    assert "B" in entities
    assert "C" not in entities


def test_traverse_no_cycles(store):
    """traverse does not loop on circular references."""
    bid = store.add_business("Corp", "enterprise")
    store.add_relationship(bid, "a", "A", "links", "B")
    store.add_relationship(bid, "b", "B", "links", "A")

    results = store.traverse("A", depth=5, business_id=bid)
    assert len(results) <= 4


def test_find_entities_matches_query(store):
    """find_entities returns entity names that appear in query."""
    bid = store.add_business("Corp", "enterprise")
    store.add_relationship(bid, "person", "Alice", "manages", "auth team")
    store.add_relationship(bid, "person", "Bob", "manages", "billing")

    matches = store.find_entities("who does Alice manage", business_id=bid)
    assert "Alice" in matches
    assert "Bob" not in matches


def test_find_entities_empty_when_no_match(store):
    """find_entities returns empty list when no entities match."""
    bid = store.add_business("Corp", "enterprise")
    store.add_relationship(bid, "person", "Alice", "manages", "auth team")

    matches = store.find_entities("what is the weather", business_id=bid)
    assert matches == []


# --- Table name validation ---


def test_archive_rejects_invalid_table(store):
    """archive() raises ValueError for invalid table names."""
    with pytest.raises(ValueError, match="Invalid table: users"):
        store.archive("users", 1)


def test_unarchive_rejects_invalid_table(store):
    """unarchive() raises ValueError for invalid table names."""
    with pytest.raises(ValueError, match="Invalid table: orders"):
        store.unarchive("orders", 1)


def test_list_archived_rejects_invalid_table(store):
    """list_archived() raises ValueError for invalid table names."""
    with pytest.raises(ValueError, match="Invalid table: sessions"):
        store.list_archived("sessions")


def test_touch_accessed_rejects_invalid_table(store):
    """touch_accessed() raises ValueError for invalid table names."""
    with pytest.raises(ValueError, match="Invalid table: logs"):
        store.touch_accessed("logs", [1, 2])


# --- Context manager ---


# --- Episode TTL / Archival ---


def test_archive_old_episodes_deletes_old(store):
    """archive_old_episodes deletes episodes older than max_age_days."""
    from datetime import datetime, timedelta

    biz_id = store.add_business("Shop", "ecommerce")

    # Insert an episode with an old timestamp directly
    old_ts = (datetime.now() - timedelta(days=400)).isoformat()
    store._conn.execute(
        "INSERT INTO episodes (business_id, task_type, task_id, summary, outcome, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (biz_id, "listing", 1, "Old episode", "success", old_ts),
    )
    store._conn.commit()

    # Insert a recent episode via the normal API
    recent_id = store.add_episode(biz_id, "listing", 2, "Recent episode", "success")

    deleted = store.archive_old_episodes(max_age_days=365)
    assert deleted == 1

    # Old episode is gone
    eps = store.get_episodes(business_id=biz_id, limit=100)
    assert len(eps) == 1
    assert eps[0]["summary"] == "Recent episode"


def test_archive_old_episodes_returns_zero_when_none_old(store):
    """archive_old_episodes returns 0 when no episodes exceed the age limit."""
    biz_id = store.add_business("Shop", "ecommerce")
    store.add_episode(biz_id, "listing", 1, "Fresh episode", "success")

    deleted = store.archive_old_episodes(max_age_days=365)
    assert deleted == 0

    eps = store.get_episodes(business_id=biz_id)
    assert len(eps) == 1


def test_archive_old_episodes_custom_max_age(store):
    """archive_old_episodes respects a custom max_age_days threshold."""
    from datetime import datetime, timedelta

    biz_id = store.add_business("Shop", "ecommerce")

    # 10-day-old episode
    ts_10d = (datetime.now() - timedelta(days=10)).isoformat()
    store._conn.execute(
        "INSERT INTO episodes (business_id, task_type, task_id, summary, outcome, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (biz_id, "listing", 1, "10 day old", "success", ts_10d),
    )
    # 50-day-old episode
    ts_50d = (datetime.now() - timedelta(days=50)).isoformat()
    store._conn.execute(
        "INSERT INTO episodes (business_id, task_type, task_id, summary, outcome, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (biz_id, "listing", 2, "50 day old", "success", ts_50d),
    )
    store._conn.commit()

    # With 30-day threshold, only the 50-day-old should be deleted
    deleted = store.archive_old_episodes(max_age_days=30)
    assert deleted == 1

    eps = store.get_episodes(business_id=biz_id, limit=100)
    assert len(eps) == 1
    assert eps[0]["summary"] == "10 day old"


def test_archive_old_episodes_empty_table(store):
    """archive_old_episodes works on an empty episodes table."""
    deleted = store.archive_old_episodes(max_age_days=365)
    assert deleted == 0


def test_archive_old_episodes_multiple_deletions(store):
    """archive_old_episodes deletes all episodes older than the threshold."""
    from datetime import datetime, timedelta

    biz_id = store.add_business("Shop", "ecommerce")

    for i in range(5):
        old_ts = (datetime.now() - timedelta(days=400 + i)).isoformat()
        store._conn.execute(
            "INSERT INTO episodes (business_id, task_type, task_id, summary, outcome, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (biz_id, "listing", i, f"Old episode {i}", "success", old_ts),
        )
    store._conn.commit()

    # Also add a recent one
    store.add_episode(biz_id, "listing", 99, "Keep this", "success")

    deleted = store.archive_old_episodes(max_age_days=365)
    assert deleted == 5

    eps = store.get_episodes(business_id=biz_id, limit=100)
    assert len(eps) == 1
    assert eps[0]["summary"] == "Keep this"


# --- Context manager ---


def test_context_manager_returns_self():
    """MemoryStore as context manager returns self."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "memory.db")
        with MemoryStore(db_path=db_path) as store:
            assert isinstance(store, MemoryStore)
            assert store._conn is not None


def test_context_manager_closes_connection():
    """MemoryStore connection is closed after exiting the with block."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "memory.db")
        with MemoryStore(db_path=db_path) as store:
            store.add_business("Test", "ecommerce")
        assert store._conn is None


def test_context_manager_closes_on_exception():
    """MemoryStore connection is closed even when an exception occurs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "memory.db")
        with pytest.raises(RuntimeError, match="boom"):
            with MemoryStore(db_path=db_path) as store:
                store.add_business("Test", "ecommerce")
                raise RuntimeError("boom")
        assert store._conn is None


# --- Hard Delete ---


def test_hard_delete_removes_row(store):
    """hard_delete returns True and the row is gone afterwards."""
    biz_id = store.add_business("Shop", "ecommerce")
    fact_id = store.add_fact(biz_id, "pricing", "avg_price", "4.99")

    result = store.hard_delete("facts", fact_id)

    assert result is True
    assert store.get_fact(fact_id) is None


def test_hard_delete_invalid_table(store):
    """hard_delete raises ValueError for a table not in the allowlist."""
    with pytest.raises(ValueError, match="Invalid table: users"):
        store.hard_delete("users", 1)


def test_hard_delete_nonexistent_id(store):
    """hard_delete returns False when the row does not exist."""
    result = store.hard_delete("facts", 9999)
    assert result is False


def test_hard_delete_business_cascade(store):
    """hard_delete_business removes the business and all child rows."""
    biz_id = store.add_business("Shop", "ecommerce")
    store.add_fact(biz_id, "pricing", "avg_price", "4.99")
    store.add_fact(biz_id, "pricing", "max_price", "9.99")
    store.add_decision(biz_id, "pricing", "Lower price", "Competition")
    store.add_learning("pricing", "Insight", source_business_id=biz_id)
    store.add_episode(biz_id, "listing", 1, "A task", "success")
    store.add_relationship(biz_id, "product", "A", "related", "B")
    store.set_state(biz_id, "listing", "L-1", "status", "active")

    counts = store.hard_delete_business(biz_id, cascade=True)

    assert counts["businesses"] == 1
    assert counts["facts"] == 2
    assert counts["decisions"] == 1
    assert counts["learnings"] == 1
    assert counts["episodes"] == 1
    assert counts["relationships"] == 1
    assert counts["state"] == 1

    # Business itself is gone
    assert store.get_business(biz_id) is None
    # No orphaned child rows remain
    assert store.get_facts(biz_id, include_archived=True) == []
    assert store.get_decisions(biz_id, include_archived=True) == []


def test_purge_archived(store):
    """purge_archived deletes all archived rows and returns the count."""
    biz_id = store.add_business("Shop", "ecommerce")
    f1 = store.add_fact(biz_id, "pricing", "k1", "v1")
    f2 = store.add_fact(biz_id, "pricing", "k2", "v2")
    f3 = store.add_fact(biz_id, "pricing", "k3", "v3")

    store.archive("facts", f1)
    store.archive("facts", f2)
    # f3 stays active

    deleted = store.purge_archived("facts")

    assert deleted == 2
    # Only the active fact remains
    remaining = store.get_facts(biz_id)
    assert len(remaining) == 1
    assert remaining[0]["id"] == f3


def test_purge_archived_with_age_filter(store):
    """purge_archived with older_than_days only removes sufficiently old rows."""
    from datetime import datetime, timedelta

    biz_id = store.add_business("Shop", "ecommerce")
    f_old = store.add_fact(biz_id, "pricing", "old_key", "old_val")
    f_new = store.add_fact(biz_id, "pricing", "new_key", "new_val")

    # Archive both facts
    store.archive("facts", f_old)
    store.archive("facts", f_new)

    # Back-date the old fact's updated_at so it appears stale
    old_ts = (datetime.now() - timedelta(days=60)).isoformat()
    store._conn.execute(
        "UPDATE facts SET updated_at = ? WHERE id = ?", (old_ts, f_old)
    )
    store._conn.commit()

    # Purge only rows archived more than 30 days ago
    deleted = store.purge_archived("facts", older_than_days=30)

    assert deleted == 1
    # The recently-archived fact still exists (as archived)
    remaining = store.list_archived("facts", business_id=biz_id)
    assert len(remaining) == 1
    assert remaining[0]["id"] == f_new


# --- Event callbacks ---


def test_memory_event_on_add_fact(store):
    """on_event callback is called with 'facts_extracted' when a fact is added."""
    events = []
    store.on_event = lambda name, data: events.append((name, data))

    biz_id = store.add_business("Shop", "ecommerce")
    fact_id = store.add_fact(biz_id, "pricing", "avg_price", "4.99")

    assert len(events) == 1
    event_name, event_data = events[0]
    assert event_name == "facts_extracted"
    assert event_data["fact_id"] == fact_id
    assert event_data["business_id"] == biz_id
    assert event_data["content"] == "4.99"


def test_memory_event_on_hard_delete(store):
    """on_event callback is called with 'item_deleted' when a row is hard-deleted."""
    biz_id = store.add_business("Shop", "ecommerce")
    fact_id = store.add_fact(biz_id, "pricing", "avg_price", "4.99")

    events = []
    store.on_event = lambda name, data: events.append((name, data))

    result = store.hard_delete("facts", fact_id)

    assert result is True
    assert len(events) == 1
    event_name, event_data = events[0]
    assert event_name == "item_deleted"
    assert event_data["table"] == "facts"
    assert event_data["item_id"] == fact_id


def test_memory_event_hard_delete_no_event_when_row_missing(store):
    """on_event is NOT called when hard_delete finds no matching row."""
    events = []
    store.on_event = lambda name, data: events.append((name, data))

    result = store.hard_delete("facts", 9999)

    assert result is False
    assert len(events) == 0


def test_memory_event_on_archive(store):
    """on_event callback is called with 'items_archived' when a fact is archived."""
    biz_id = store.add_business("Shop", "ecommerce")
    fact_id = store.add_fact(biz_id, "pricing", "avg_price", "4.99")

    events = []
    store.on_event = lambda name, data: events.append((name, data))

    store.archive("facts", fact_id)

    assert len(events) == 1
    event_name, event_data = events[0]
    assert event_name == "items_archived"
    assert event_data["table"] == "facts"
    assert event_data["ids"] == [fact_id]


def test_memory_event_callback_error_swallowed(store):
    """A callback that raises an exception does not crash the caller."""
    def bad_callback(name, data):
        raise RuntimeError("callback exploded")

    store.on_event = bad_callback

    biz_id = store.add_business("Shop", "ecommerce")
    # Should not raise, even though the callback raises
    fact_id = store.add_fact(biz_id, "pricing", "avg_price", "4.99")

    # The fact was still stored successfully despite the bad callback
    fact = store.get_fact(fact_id)
    assert fact is not None
    assert fact["value"] == "4.99"


def test_memory_event_no_callback_by_default(store):
    """MemoryStore does not fire events when on_event is None (default)."""
    # This test verifies there is no crash when on_event is unset
    biz_id = store.add_business("Shop", "ecommerce")
    fact_id = store.add_fact(biz_id, "pricing", "avg_price", "4.99")
    store.hard_delete("facts", fact_id)
    # If we get here without error, the default (no callback) works correctly


def test_fact_updated_event(store):
    """update_fact emits a 'fact_updated' event with the fact_id and new content."""
    events = []
    store.on_event = lambda name, data: events.append((name, data))

    biz_id = store.add_business("Shop", "ecommerce")
    # Clear the facts_extracted event from add_fact
    fact_id = store.add_fact(biz_id, "pricing", "avg_price", "4.99")
    events.clear()

    store.update_fact(fact_id, value="5.99", confidence=90)

    assert len(events) == 1
    event_name, event_data = events[0]
    assert event_name == "fact_updated"
    assert event_data["fact_id"] == fact_id
    assert event_data["content"] == "5.99"


def test_fact_updated_event_no_value_change(store):
    """update_fact emits 'fact_updated' even when only non-value fields change; content is absent."""
    events = []
    store.on_event = lambda name, data: events.append((name, data))

    biz_id = store.add_business("Shop", "ecommerce")
    fact_id = store.add_fact(biz_id, "pricing", "avg_price", "4.99")
    events.clear()

    store.update_fact(fact_id, confidence=80)

    assert len(events) == 1
    event_name, event_data = events[0]
    assert event_name == "fact_updated"
    assert event_data["fact_id"] == fact_id
    # No "value" kwarg was passed so "content" is absent from the payload
    assert "content" not in event_data


# --- Episode deduplication ---


def test_episode_dedup_same_content(store):
    """Adding the same episode twice within an hour returns the existing ID and stores only one row."""
    biz_id = store.add_business("Shop", "ecommerce")

    ep_id_1 = store.add_episode(biz_id, "listing", 1, "Created a listing", "success")
    ep_id_2 = store.add_episode(biz_id, "listing", 2, "Created a listing", "success")

    assert ep_id_1 == ep_id_2

    eps = store.get_episodes(business_id=biz_id, limit=100)
    assert len(eps) == 1


def test_episode_dedup_different_content(store):
    """Episodes with different summaries are both stored."""
    biz_id = store.add_business("Shop", "ecommerce")

    ep_id_1 = store.add_episode(biz_id, "listing", 1, "Created a listing", "success")
    ep_id_2 = store.add_episode(biz_id, "listing", 2, "Updated a listing", "success")

    assert ep_id_1 != ep_id_2

    eps = store.get_episodes(business_id=biz_id, limit=100)
    assert len(eps) == 2


def test_episode_dedup_after_window(store):
    """An episode whose identical twin is older than one hour is stored as a new row."""
    from datetime import datetime, timedelta

    biz_id = store.add_business("Shop", "ecommerce")

    # Insert the "old" episode directly with a timestamp just over an hour ago.
    old_ts = (datetime.now() - timedelta(hours=2)).isoformat()
    store._conn.execute(
        "INSERT INTO episodes (business_id, task_type, task_id, summary, outcome, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (biz_id, "listing", 1, "Created a listing", "success", old_ts),
    )
    store._conn.commit()

    # Now add the same episode through the normal API — it should NOT be deduped.
    ep_id_new = store.add_episode(biz_id, "listing", 2, "Created a listing", "success")

    eps = store.get_episodes(business_id=biz_id, limit=100)
    assert len(eps) == 2
    # The new episode has its own fresh ID
    ids = {ep["id"] for ep in eps}
    assert ep_id_new in ids

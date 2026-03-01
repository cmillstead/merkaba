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

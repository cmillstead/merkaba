# tests/test_memory_vectors.py
import sys
import tempfile
import os
from unittest.mock import MagicMock

import pytest

try:
    import chromadb
    HAS_CHROMADB = True
except ImportError:
    HAS_CHROMADB = False


def _ollama_is_reachable():
    """Check if Ollama is running (runtime check, not import-time)."""
    try:
        import httpx
        resp = httpx.get("http://localhost:11434/api/tags", timeout=2)
        return resp.status_code == 200
    except Exception:
        return False


requires_chromadb_and_real_ollama = pytest.mark.skipif(
    not HAS_CHROMADB,
    reason="Requires chromadb",
)


@pytest.fixture(autouse=True)
def _real_ollama_or_skip():
    """Swap the mocked ollama for the real module, or skip if unavailable."""
    if not _ollama_is_reachable():
        pytest.skip("Ollama not reachable at localhost:11434")

    # Save the mock and import the real module
    mock = sys.modules.get("ollama")
    if mock and isinstance(mock, MagicMock):
        del sys.modules["ollama"]
        # Also clear submodule caches so VectorMemory picks up the real client
        for key in list(sys.modules):
            if key.startswith("ollama."):
                del sys.modules[key]

    try:
        import importlib
        real_ollama = importlib.import_module("ollama")
    except ImportError:
        pytest.skip("Real ollama module not installed")

    yield

    # Restore the mock so other tests are unaffected
    if mock is not None:
        sys.modules["ollama"] = mock
        # Clear real ollama submodule caches to prevent leakage
        for key in list(sys.modules):
            if key.startswith("ollama."):
                del sys.modules[key]


@requires_chromadb_and_real_ollama
@pytest.mark.integration
class TestVectorMemory:
    """Integration tests for VectorMemory (requires ChromaDB + Ollama)."""

    def _make_vector_memory(self, tmpdir):
        from merkaba.memory.vectors import VectorMemory
        return VectorMemory(persist_dir=tmpdir)

    def test_creation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            vm = self._make_vector_memory(tmpdir)
            assert vm._client is not None
            vm.close()

    def test_index_and_search_facts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            vm = self._make_vector_memory(tmpdir)
            vm.index_fact(1, 1, "Average price for watercolor clipart is $4.99")
            vm.index_fact(2, 1, "Best selling tags are boho and minimalist")
            vm.index_fact(3, 2, "SaaS monthly churn rate is 5%")

            results = vm.search_facts("clipart pricing", business_id=1, limit=2)
            assert len(results) > 0
            assert results[0]["id"] in (1, 2)
            vm.close()

    def test_index_and_search_decisions(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            vm = self._make_vector_memory(tmpdir)
            vm.index_decision(1, 1, "Lowered price from $5.99 to $3.99 due to competition")
            vm.index_decision(2, 1, "Added free shipping for orders over $20")

            results = vm.search_decisions("price change", limit=2)
            assert len(results) > 0
            vm.close()

    def test_index_and_search_learnings(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            vm = self._make_vector_memory(tmpdir)
            vm.index_learning(1, "Posting at 9am EST gets 30% more engagement")
            vm.index_learning(2, "Seasonal items sell 3x during holidays")

            results = vm.search_learnings("best time to post", limit=2)
            assert len(results) > 0
            vm.close()

    def test_search_empty_collection(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            vm = self._make_vector_memory(tmpdir)
            results = vm.search_facts("anything", limit=5)
            assert results == []
            vm.close()

    def test_business_id_filtering(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            vm = self._make_vector_memory(tmpdir)
            vm.index_fact(1, 1, "Shop A sells clipart")
            vm.index_fact(2, 2, "Shop B sells templates")

            results_1 = vm.search_facts("sells", business_id=1, limit=5)
            results_2 = vm.search_facts("sells", business_id=2, limit=5)

            # Each should only return facts for the filtered business
            for r in results_1:
                assert r["metadata"]["business_id"] == 1
            for r in results_2:
                assert r["metadata"]["business_id"] == 2
            vm.close()


@requires_chromadb_and_real_ollama
@pytest.mark.integration
def test_delete_vectors_removes_entries(tmp_path):
    """delete_vectors removes specific IDs from a collection."""
    from merkaba.memory.vectors import VectorMemory

    try:
        vm = VectorMemory(persist_dir=str(tmp_path / "vectors"))
    except (ImportError, Exception):
        pytest.skip("ChromaDB or Ollama not available")

    vm.index_fact(1, 0, "test fact one")
    vm.index_fact(2, 0, "test fact two")

    vm.delete_vectors("facts", ["1"])

    results = vm.search_facts("test fact", limit=10)
    ids = [r["id"] for r in results]
    assert 1 not in ids
    assert 2 in ids


@requires_chromadb_and_real_ollama
@pytest.mark.integration
def test_rebuild_from_store_excludes_archived(tmp_path):
    """rebuild_from_store re-indexes only non-archived items."""
    from merkaba.memory.vectors import VectorMemory
    from merkaba.memory.store import MemoryStore

    store = MemoryStore(db_path=str(tmp_path / "memory.db"))
    try:
        vm = VectorMemory(persist_dir=str(tmp_path / "vectors"))
    except (ImportError, Exception):
        store.close()
        pytest.skip("ChromaDB or Ollama not available")

    bid = store.add_business("Shop", "ecommerce")
    f1 = store.add_fact(bid, "pricing", "active", "10.00")
    f2 = store.add_fact(bid, "pricing", "archived_item", "5.00")
    store.archive("facts", f2)

    vm.index_fact(f1, bid, "pricing: active = 10.00")
    vm.index_fact(f2, bid, "pricing: archived_item = 5.00")

    vm.rebuild_from_store(store)

    results = vm.search_facts("pricing", limit=10)
    ids = [r["id"] for r in results]
    assert f1 in ids
    assert f2 not in ids

    store.close()


@requires_chromadb_and_real_ollama
@pytest.mark.integration
def test_delete_vectors_for_business(tmp_path):
    """delete_vectors_for_business removes all vectors for a specific business."""
    from merkaba.memory.vectors import VectorMemory

    try:
        vm = VectorMemory(persist_dir=str(tmp_path / "vectors"))
    except (ImportError, Exception):
        pytest.skip("ChromaDB or Ollama not available")

    # Index facts and decisions for two businesses
    vm.index_fact(1, 1, "business 1 fact alpha")
    vm.index_fact(2, 1, "business 1 fact beta")
    vm.index_fact(3, 2, "business 2 fact gamma")
    vm.index_decision(10, 1, "business 1 decision one")
    vm.index_decision(11, 2, "business 2 decision two")

    # Delete vectors for business 1
    counts = vm.delete_vectors_for_business(1)
    assert counts["facts"] == 2
    assert counts["decisions"] == 1

    # Business 2 vectors should still exist
    facts_results = vm.search_facts("business fact", limit=10)
    fact_ids = [r["id"] for r in facts_results]
    assert 1 not in fact_ids
    assert 2 not in fact_ids
    assert 3 in fact_ids

    decision_results = vm.search_decisions("business decision", limit=10)
    dec_ids = [r["id"] for r in decision_results]
    assert 10 not in dec_ids
    assert 11 in dec_ids

    vm.close()


@requires_chromadb_and_real_ollama
@pytest.mark.integration
def test_delete_vectors_for_business_empty(tmp_path):
    """delete_vectors_for_business returns zero counts for nonexistent business."""
    from merkaba.memory.vectors import VectorMemory

    try:
        vm = VectorMemory(persist_dir=str(tmp_path / "vectors"))
    except (ImportError, Exception):
        pytest.skip("ChromaDB or Ollama not available")

    vm.index_fact(1, 1, "some fact")

    counts = vm.delete_vectors_for_business(999)
    assert counts["facts"] == 0
    assert counts["decisions"] == 0
    vm.close()

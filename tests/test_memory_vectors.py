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

# These tests need the REAL ollama module (not a MagicMock).
# The conftest installs a mock for unit tests. If ollama is mocked,
# ChromaDB's OllamaEmbeddingFunction will get a MagicMock Client
# and embeddings will be empty.
_OLLAMA_IS_REAL = "ollama" in sys.modules and not isinstance(sys.modules["ollama"], MagicMock)

requires_chromadb_and_real_ollama = pytest.mark.skipif(
    not HAS_CHROMADB or not _OLLAMA_IS_REAL,
    reason="Requires chromadb and real (non-mocked) ollama module with running Ollama",
)


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

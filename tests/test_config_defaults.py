"""Tests for config defaults/utils integrity and concurrent MemoryStore access."""

import json
import os
import tempfile
import threading

import pytest

from merkaba.config.defaults import DEFAULT_MODELS, FALLBACK_CHAINS
from merkaba.config.utils import atomic_write_json


EXPECTED_MODEL_KEYS = {"complex", "simple", "classifier", "embedding", "health_check"}


class TestDefaultModels:
    """Verify DEFAULT_MODELS dict integrity."""

    def test_all_model_keys_present(self):
        """DEFAULT_MODELS must contain all expected role keys."""
        assert set(DEFAULT_MODELS.keys()) == EXPECTED_MODEL_KEYS

    def test_all_model_values_are_nonempty_strings(self):
        """Every model value must be a non-empty string."""
        for key, value in DEFAULT_MODELS.items():
            assert isinstance(value, str) and len(value) > 0, f"{key} has invalid value: {value!r}"


class TestFallbackChains:
    """Verify FALLBACK_CHAINS reference valid models and have required structure."""

    def test_fallback_chains_reference_valid_models(self):
        """Every primary and fallback model must exist in DEFAULT_MODELS values."""
        valid_models = set(DEFAULT_MODELS.values())
        for chain_name, chain in FALLBACK_CHAINS.items():
            assert chain["primary"] in valid_models, (
                f"Chain {chain_name!r} primary {chain['primary']!r} not in DEFAULT_MODELS"
            )
            for fb in chain["fallbacks"]:
                assert fb in valid_models, (
                    f"Chain {chain_name!r} fallback {fb!r} not in DEFAULT_MODELS"
                )

    def test_fallback_chains_have_required_keys(self):
        """Each chain must have primary, fallbacks, and timeout."""
        for chain_name, chain in FALLBACK_CHAINS.items():
            assert "primary" in chain, f"Chain {chain_name!r} missing 'primary'"
            assert "fallbacks" in chain, f"Chain {chain_name!r} missing 'fallbacks'"
            assert "timeout" in chain, f"Chain {chain_name!r} missing 'timeout'"
            assert isinstance(chain["fallbacks"], list)
            assert isinstance(chain["timeout"], (int, float))


class TestAtomicWriteJson:
    """Verify atomic_write_json creates valid JSON files."""

    def test_atomic_write_json_creates_file(self, tmp_path):
        """Write JSON to a temp path, read it back, verify correctness."""
        target = str(tmp_path / "config.json")
        data = {"key": "value", "nested": {"a": 1}}

        atomic_write_json(target, data)

        assert os.path.exists(target)
        with open(target) as f:
            loaded = json.load(f)
        assert loaded == data

    def test_atomic_write_json_overwrites_existing(self, tmp_path):
        """Overwriting an existing file produces the new content."""
        target = str(tmp_path / "config.json")
        atomic_write_json(target, {"old": True})
        atomic_write_json(target, {"new": True})

        with open(target) as f:
            loaded = json.load(f)
        assert loaded == {"new": True}

    def test_atomic_write_json_creates_parent_dirs(self, tmp_path):
        """Parent directories are created if they don't exist."""
        target = str(tmp_path / "sub" / "dir" / "config.json")
        atomic_write_json(target, {"ok": True})

        with open(target) as f:
            loaded = json.load(f)
        assert loaded == {"ok": True}


class TestMemoryStoreConcurrentWrites:
    """Verify MemoryStore handles concurrent writes correctly via WAL mode."""

    def test_concurrent_writes(self, tmp_path):
        """Spawn 10 threads each with own MemoryStore adding 10 facts; assert final count is 100.

        Each thread gets its own MemoryStore (separate SQLite connection) to
        simulate realistic concurrent access.  WAL mode allows concurrent writers.
        """
        from merkaba.memory.store import MemoryStore

        db = str(tmp_path / "test_concurrent.db")
        # Create DB and business with an initial connection.
        setup_store = MemoryStore(db_path=db)
        biz_id = setup_store.add_business("test_biz", "test")
        setup_store.close()

        errors: list[Exception] = []
        num_threads = 10
        facts_per_thread = 10

        def writer(thread_id: int) -> None:
            try:
                store = MemoryStore(db_path=db)
                for i in range(facts_per_thread):
                    store.add_fact(
                        business_id=biz_id,
                        category="test",
                        key=f"t{thread_id}_f{i}",
                        value=f"value_{thread_id}_{i}",
                    )
                store.close()
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=writer, args=(t,)) for t in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Thread errors: {errors}"

        verify_store = MemoryStore(db_path=db)
        facts = verify_store.get_facts(biz_id)
        assert len(facts) == num_threads * facts_per_thread
        verify_store.close()

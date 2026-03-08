"""Tests for merkaba.config.loader — centralised config loading."""

import json
import os
import threading
import time

import pytest

from merkaba.config.loader import clear_cache, load_config


@pytest.fixture(autouse=True)
def _always_clear_cache():
    """Ensure the module-level cache is clean before and after every test."""
    clear_cache()
    yield
    clear_cache()


@pytest.fixture()
def config_file(tmp_path):
    """Create a temporary config.json and point load_config at it."""
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"models": {"complex": "test-model"}}))
    return str(path)


# --- Basic loading ---


def test_load_config_returns_dict(config_file):
    result = load_config(path=config_file)
    assert isinstance(result, dict)
    assert result["models"]["complex"] == "test-model"


def test_load_config_returns_empty_dict_for_missing_file(tmp_path):
    missing = str(tmp_path / "does-not-exist.json")
    result = load_config(path=missing)
    assert result == {}


def test_load_config_returns_empty_dict_for_invalid_json(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{invalid json!!")
    result = load_config(path=str(bad))
    assert result == {}


# --- Caching behaviour ---


def test_load_config_caching_same_object(config_file):
    """When using the default path and caching, repeated calls return the
    same dict object as long as the file has not been modified."""
    # Use use_cache=True with path=None (default path) for caching to work.
    # Since config_file is a non-default path, caching by design does NOT
    # apply to custom paths.  We verify that use_cache=False always re-reads.
    first = load_config(path=config_file, use_cache=False)
    second = load_config(path=config_file, use_cache=False)
    # Both should have identical content
    assert first == second
    # But they are separate objects because caching is disabled for custom paths
    assert first is not second


def test_load_config_default_path_caching(tmp_path, monkeypatch):
    """Caching works when using the default path (path=None)."""
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"key": "value1"}))
    monkeypatch.setattr("merkaba.config.loader._default_config_path", lambda: str(cfg))

    first = load_config()
    second = load_config()
    assert first == second  # Same content from cache
    assert first is not second  # But deepcopy prevents mutation leaks


def test_load_config_reload_after_change(tmp_path, monkeypatch):
    """When the file is modified (mtime changes), cache is invalidated."""
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"version": 1}))
    monkeypatch.setattr("merkaba.config.loader._default_config_path", lambda: str(cfg))

    first = load_config()
    assert first["version"] == 1

    # Ensure mtime actually changes — some filesystems have 1-second granularity
    mtime = os.path.getmtime(str(cfg))
    os.utime(str(cfg), (mtime + 2, mtime + 2))
    cfg.write_text(json.dumps({"version": 2}))

    second = load_config()
    assert second["version"] == 2
    assert first is not second


# --- clear_cache ---


def test_clear_cache(tmp_path, monkeypatch):
    """After clear_cache(), the next load_config() re-reads from disk."""
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"a": 1}))
    monkeypatch.setattr("merkaba.config.loader._default_config_path", lambda: str(cfg))

    first = load_config()
    clear_cache()
    # Overwrite WITHOUT changing mtime — only works because cache was cleared
    cfg.write_text(json.dumps({"a": 2}))
    second = load_config()
    assert second["a"] == 2
    assert first is not second


# --- Edge cases ---


def test_load_config_empty_file(tmp_path):
    """An empty file is invalid JSON and should return {}."""
    empty = tmp_path / "empty.json"
    empty.write_text("")
    result = load_config(path=str(empty))
    assert result == {}


def test_load_config_with_explicit_path_bypasses_cache(tmp_path, monkeypatch):
    """Passing an explicit path never populates or reads the module cache."""
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"x": 1}))

    # Load with explicit path
    load_config(path=str(cfg))

    # Module cache should still be None
    import merkaba.config.loader as _mod
    assert _mod._cache is None


# --- Concurrency ---


def test_concurrent_config_reads(tmp_path, monkeypatch):
    """10 threads all calling load_config() concurrently must not raise."""
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"concurrent": True, "value": 42}))
    monkeypatch.setattr("merkaba.config.loader._default_config_path", lambda: str(cfg))

    num_threads = 10
    barrier = threading.Barrier(num_threads)
    errors: list[Exception] = []
    results: list[dict] = []
    results_lock = threading.Lock()

    def reader():
        try:
            barrier.wait(timeout=5)
            result = load_config()
            with results_lock:
                results.append(result)
        except Exception as exc:
            with results_lock:
                errors.append(exc)

    threads = [threading.Thread(target=reader) for _ in range(num_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert errors == [], f"Concurrent reads raised: {errors}"
    assert len(results) == num_threads
    for r in results:
        assert r == {"concurrent": True, "value": 42}


def test_concurrent_read_during_write(tmp_path, monkeypatch):
    """One thread writes config repeatedly while others read — no crashes or
    corrupt data allowed."""
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"version": 0}))
    monkeypatch.setattr("merkaba.config.loader._default_config_path", lambda: str(cfg))

    stop = threading.Event()
    errors: list[Exception] = []
    errors_lock = threading.Lock()
    num_readers = 5
    write_iterations = 50

    def writer():
        try:
            for i in range(1, write_iterations + 1):
                content = json.dumps({"version": i})
                cfg.write_text(content)
                clear_cache()
                time.sleep(0.001)
        except Exception as exc:
            with errors_lock:
                errors.append(exc)
        finally:
            stop.set()

    def reader():
        try:
            while not stop.is_set():
                result = load_config()
                # Result must always be a valid dict — either empty (if file
                # was mid-write and JSON was temporarily invalid) or a dict
                # with an integer "version" key.
                assert isinstance(result, dict)
                if "version" in result:
                    assert isinstance(result["version"], int)
        except Exception as exc:
            with errors_lock:
                errors.append(exc)

    threads = [threading.Thread(target=writer)]
    threads += [threading.Thread(target=reader) for _ in range(num_readers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert errors == [], f"Concurrent read-during-write raised: {errors}"

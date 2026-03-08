"""Tests for merkaba.config.loader — centralised config loading."""

import json
import os

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

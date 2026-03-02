# tests/test_hot_reload.py
"""Tests for hot-reloadable configuration with mtime checking."""

import json
import threading
import time
from pathlib import Path
from merkaba.config.hot_reload import HotConfig, ConfigSnapshot


def test_config_snapshot_loads(tmp_path):
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({"model": "qwen3:8b"}))
    snap = ConfigSnapshot(config_file)
    snap.reload()
    assert snap.data["model"] == "qwen3:8b"


def test_config_snapshot_detects_stale(tmp_path):
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({"v": 1}))
    snap = ConfigSnapshot(config_file)
    snap.reload()
    assert not snap.is_stale()

    time.sleep(0.05)
    config_file.write_text(json.dumps({"v": 2}))
    assert snap.is_stale()


def test_hot_config_reloads_on_change(tmp_path):
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({"models": {"complex": "qwen3.5:122b"}}))

    hc = HotConfig(config_file)
    assert hc.get("models")["complex"] == "qwen3.5:122b"

    time.sleep(0.05)
    config_file.write_text(json.dumps({"models": {"complex": "llama3:70b"}}))
    assert hc.get("models")["complex"] == "llama3:70b"


def test_hot_config_survives_bad_json(tmp_path):
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({"valid": True}))

    hc = HotConfig(config_file)
    assert hc.get("valid") is True

    time.sleep(0.05)
    config_file.write_text("NOT VALID JSON {{{")
    assert hc.get("valid") is True  # Keeps previous


def test_hot_config_fires_callback(tmp_path):
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({"a": 1}))

    hc = HotConfig(config_file)
    changes = []
    hc.on_change(lambda keys, old, new: changes.append(keys))

    time.sleep(0.05)
    config_file.write_text(json.dumps({"a": 2}))
    hc.get("a")  # Triggers reload

    assert len(changes) == 1
    assert "a" in changes[0]


def test_hot_config_logs_security_changes(tmp_path, caplog):
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({"permissions": "strict"}))

    hc = HotConfig(config_file)
    time.sleep(0.05)
    config_file.write_text(json.dumps({"permissions": "lax"}))

    import logging
    with caplog.at_level(logging.WARNING, logger="merkaba.config"):
        hc.get("permissions")

    assert "Security-relevant config changed" in caplog.text


def test_hot_config_concurrent_access(tmp_path):
    """Multiple threads calling get() during reload don't crash or corrupt."""
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({"counter": 0}))
    hc = HotConfig(config_file)
    errors = []

    def reader():
        for _ in range(100):
            try:
                val = hc.get("counter")
                assert isinstance(val, int)
            except Exception as e:
                errors.append(e)

    threads = [threading.Thread(target=reader) for _ in range(4)]

    def writer():
        for i in range(50):
            time.sleep(0.001)
            config_file.write_text(json.dumps({"counter": i}))

    threads.append(threading.Thread(target=writer))
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors

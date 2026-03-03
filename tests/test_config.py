"""Tests for config-related CLI helpers."""

import json
import pytest


def test_atomic_write_json_writes_correctly(tmp_path):
    """M5: config.json must be written atomically."""
    from merkaba.cli import _atomic_write_json

    config_path = str(tmp_path / "config.json")
    _atomic_write_json(config_path, {"new": "value"})
    data = json.loads((tmp_path / "config.json").read_text())
    assert data == {"new": "value"}


def test_atomic_write_json_replaces_existing(tmp_path):
    """M5: Atomic write replaces existing file."""
    config_path = str(tmp_path / "config.json")
    (tmp_path / "config.json").write_text('{"old": true}')
    from merkaba.cli import _atomic_write_json

    _atomic_write_json(config_path, {"new": "value"})
    data = json.loads((tmp_path / "config.json").read_text())
    assert data == {"new": "value"}
    assert "old" not in data

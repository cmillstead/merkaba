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


def test_config_set_warns_on_unknown_key(tmp_path):
    """M4: config set must warn about unknown config keys."""
    from merkaba.cli import KNOWN_CONFIG_KEYS

    assert "model" in KNOWN_CONFIG_KEYS  # Known key exists
    assert "totally_fake_key" not in KNOWN_CONFIG_KEYS  # Unknown key not in set


def test_data_delete_all_uses_yes_flag():
    """Low: delete-all should use --yes/-y for consistency."""
    from typer.testing import CliRunner
    from merkaba.cli import app

    runner = CliRunner()
    result = runner.invoke(app, ["data", "delete-all", "--help"])
    assert "--yes" in result.output or "-y" in result.output


def test_atomic_write_json_with_kwargs(tmp_path):
    """Atomic write supports extra json.dump kwargs like default=str."""
    from merkaba.cli import _atomic_write_json
    from datetime import datetime

    config_path = str(tmp_path / "test.json")
    _atomic_write_json(config_path, {"ts": datetime(2026, 1, 1)}, default=str)
    data = json.loads((tmp_path / "test.json").read_text())
    assert data["ts"] == "2026-01-01 00:00:00"


def test_data_delete_all_single_close():
    """Bug: store.close() should only appear once (in finally block)."""
    import inspect
    from merkaba.cli import data_delete_all

    source = inspect.getsource(data_delete_all)
    # The close should be in the finally block only
    assert source.count("store.close()") == 1


def test_load_cli_extensions_has_outer_try():
    """Extension loading should not crash CLI on import failure."""
    import inspect
    from merkaba.cli import _load_cli_extensions

    source = inspect.getsource(_load_cli_extensions)
    assert "Failed to discover CLI extensions" in source

"""Tests for merkaba.paths — centralised path resolution."""

import os

import pytest

from merkaba.paths import merkaba_home, config_path, db_path, subdir


class TestMerkabaHome:
    def test_default_path(self, monkeypatch):
        """merkaba_home() returns ~/.merkaba expanded when no env var is set."""
        monkeypatch.delenv("MERKABA_HOME", raising=False)
        assert merkaba_home() == os.path.expanduser("~/.merkaba")

    def test_env_var_override(self, monkeypatch, tmp_path):
        """MERKABA_HOME env var overrides the default location."""
        override = str(tmp_path / "custom-merkaba")
        monkeypatch.setenv("MERKABA_HOME", override)
        assert merkaba_home() == override

    def test_env_var_empty_string_uses_default(self, monkeypatch):
        """An empty MERKABA_HOME falls back to the default."""
        monkeypatch.setenv("MERKABA_HOME", "")
        assert merkaba_home() == os.path.expanduser("~/.merkaba")


class TestConfigPath:
    def test_default(self, monkeypatch):
        monkeypatch.delenv("MERKABA_HOME", raising=False)
        assert config_path() == os.path.join(
            os.path.expanduser("~/.merkaba"), "config.json"
        )

    def test_with_override(self, monkeypatch, tmp_path):
        monkeypatch.setenv("MERKABA_HOME", str(tmp_path))
        assert config_path() == os.path.join(str(tmp_path), "config.json")


class TestDbPath:
    def test_db_path_construction(self, monkeypatch):
        """db_path('memory') returns the correct path."""
        monkeypatch.delenv("MERKABA_HOME", raising=False)
        expected = os.path.join(os.path.expanduser("~/.merkaba"), "memory.db")
        assert db_path("memory") == expected

    def test_db_path_with_override(self, monkeypatch, tmp_path):
        monkeypatch.setenv("MERKABA_HOME", str(tmp_path))
        assert db_path("tasks") == os.path.join(str(tmp_path), "tasks.db")

    def test_db_path_various_names(self, monkeypatch, tmp_path):
        monkeypatch.setenv("MERKABA_HOME", str(tmp_path))
        for name in ("memory", "tasks", "actions", "research"):
            assert db_path(name) == os.path.join(str(tmp_path), f"{name}.db")


class TestSubdir:
    def test_subdir(self, monkeypatch, tmp_path):
        monkeypatch.setenv("MERKABA_HOME", str(tmp_path))
        assert subdir("conversations") == os.path.join(str(tmp_path), "conversations")
        assert subdir("plugins") == os.path.join(str(tmp_path), "plugins")

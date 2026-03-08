# tests/test_backup_safety.py
"""Tests for backup safety hardening: permissions, secret stripping, warnings."""

import json
import logging
import os
import platform
import sqlite3
import stat
from pathlib import Path
from unittest.mock import patch

import pytest

from merkaba.config.utils import _SECRET_KEY_NAMES, deep_strip_secrets
from merkaba.orchestration.backup import BackupManager


def _make_db(path: Path, table: str = "test", rows: list[tuple] = None):
    """Create a real SQLite DB with optional data."""
    conn = sqlite3.connect(str(path))
    conn.execute(f"CREATE TABLE {table} (id INTEGER PRIMARY KEY, value TEXT)")
    for row in rows or []:
        conn.execute(f"INSERT INTO {table} (id, value) VALUES (?, ?)", row)
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# deep_strip_secrets unit tests
# ---------------------------------------------------------------------------


class TestDeepStripSecrets:
    """Verify deep_strip_secrets removes secret keys entirely."""

    def test_strips_top_level_secrets(self):
        config = {
            "api_key": "sk-abc123",
            "model": "qwen3:8b",
            "password": "hunter2",
        }
        result = deep_strip_secrets(config)
        assert "api_key" not in result
        assert "password" not in result
        assert result["model"] == "qwen3:8b"

    def test_strips_nested_secrets(self):
        config = {
            "llm": {
                "provider": "anthropic",
                "api_key": "sk-nested-key",
            },
            "security": {
                "totp_secret": "JBSWY3DPEHPK3PXP",
                "enabled": True,
            },
        }
        result = deep_strip_secrets(config)
        assert "api_key" not in result["llm"]
        assert result["llm"]["provider"] == "anthropic"
        assert "totp_secret" not in result["security"]
        assert result["security"]["enabled"] is True

    def test_strips_deeply_nested_secrets(self):
        config = {
            "level1": {
                "level2": {
                    "level3": {
                        "token": "deep-secret",
                        "safe_key": "visible",
                    }
                }
            }
        }
        result = deep_strip_secrets(config)
        assert "token" not in result["level1"]["level2"]["level3"]
        assert result["level1"]["level2"]["level3"]["safe_key"] == "visible"

    def test_does_not_modify_original(self):
        config = {"api_key": "original", "name": "test"}
        deep_strip_secrets(config)
        assert config["api_key"] == "original"

    def test_strips_all_secret_key_names(self):
        config = {name: f"value-{name}" for name in _SECRET_KEY_NAMES}
        config["safe"] = "keep-me"
        result = deep_strip_secrets(config)
        for name in _SECRET_KEY_NAMES:
            assert name not in result, f"Expected {name!r} to be stripped"
        assert result["safe"] == "keep-me"

    def test_empty_config(self):
        assert deep_strip_secrets({}) == {}

    def test_no_secrets_unchanged(self):
        config = {"model": "qwen3:8b", "max_tokens": 4096}
        assert deep_strip_secrets(config) == config


# ---------------------------------------------------------------------------
# Backup directory secure permissions
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    platform.system() == "Windows",
    reason="File permission enforcement is Unix-only",
)
class TestBackupSecurePermissions:
    """Verify backup directories get restrictive permissions."""

    def test_backup_dir_gets_secure_permissions(self, tmp_path):
        _make_db(tmp_path / "memory.db")

        mgr = BackupManager(merkaba_dir=tmp_path)
        result = mgr.run_backup()

        # Both the parent backup dir and the timestamped dir should be 0o700
        backup_dir = tmp_path / "backups"
        assert stat.S_IMODE(os.stat(str(backup_dir)).st_mode) == 0o700
        assert stat.S_IMODE(os.stat(str(result)).st_mode) == 0o700

    def test_backup_with_ensure_secure_permissions_unavailable(self, tmp_path):
        """Backup should still succeed if ensure_secure_permissions is None."""
        _make_db(tmp_path / "memory.db")

        with patch(
            "merkaba.orchestration.backup.ensure_secure_permissions", None
        ):
            mgr = BackupManager(merkaba_dir=tmp_path)
            result = mgr.run_backup()

        assert result.exists()
        assert (result / "memory.db").exists()


# ---------------------------------------------------------------------------
# Config secret stripping in backups
# ---------------------------------------------------------------------------


class TestBackupConfigStripping:
    """Verify config.json in backup has sensitive keys stripped."""

    def test_backup_config_has_secrets_stripped(self, tmp_path):
        _make_db(tmp_path / "memory.db")
        config = {
            "api_key": "sk-secret-key-12345",
            "model": "qwen3:8b",
            "llm": {
                "provider": "anthropic",
                "api_key": "sk-ant-nested",
                "max_tokens": 4096,
            },
            "security": {
                "totp_secret": "JBSWY3DPEHPK3PXP",
                "encryption_key": "fernet-key-here",
                "enabled": True,
            },
            "password": "hunter2",
            "token": "tok-abc",
            "secret": "mysecret",
        }
        (tmp_path / "config.json").write_text(json.dumps(config))

        mgr = BackupManager(merkaba_dir=tmp_path)
        result = mgr.run_backup()

        backed_config = json.loads((result / "config.json").read_text())

        # All secret keys should be gone
        assert "api_key" not in backed_config
        assert "password" not in backed_config
        assert "token" not in backed_config
        assert "secret" not in backed_config

        # Nested secrets should also be gone
        assert "api_key" not in backed_config["llm"]
        assert "totp_secret" not in backed_config["security"]
        assert "encryption_key" not in backed_config["security"]

        # Non-secret values should be preserved
        assert backed_config["model"] == "qwen3:8b"
        assert backed_config["llm"]["provider"] == "anthropic"
        assert backed_config["llm"]["max_tokens"] == 4096
        assert backed_config["security"]["enabled"] is True

    def test_original_config_not_modified(self, tmp_path):
        """The source config.json must NOT be altered by the backup."""
        _make_db(tmp_path / "memory.db")
        config = {"api_key": "sk-original", "model": "qwen3:8b"}
        (tmp_path / "config.json").write_text(json.dumps(config))

        mgr = BackupManager(merkaba_dir=tmp_path)
        mgr.run_backup()

        original = json.loads((tmp_path / "config.json").read_text())
        assert original["api_key"] == "sk-original"

    def test_invalid_config_json_skips_backup_with_warning(self, tmp_path, caplog):
        """If config.json is not valid JSON, skip it with a warning (don't copy secrets)."""
        _make_db(tmp_path / "memory.db")
        (tmp_path / "config.json").write_text("not valid json {{{")

        with caplog.at_level(logging.WARNING, logger="merkaba.orchestration.backup"):
            mgr = BackupManager(merkaba_dir=tmp_path)
            result = mgr.run_backup()

        # Config should NOT be copied (no plaintext fallback)
        assert not (result / "config.json").exists()

        # Warning about skipping
        assert any(
            "strip secrets" in r.message.lower() or "skipping" in r.message.lower()
            for r in caplog.records
        )


# ---------------------------------------------------------------------------
# Unencrypted backup warning
# ---------------------------------------------------------------------------


class TestUnencryptedBackupWarning:
    """Verify unencrypted backups emit a warning."""

    def test_unencrypted_backup_emits_warning(self, tmp_path, caplog):
        _make_db(tmp_path / "memory.db")

        with caplog.at_level(logging.WARNING, logger="merkaba.orchestration.backup"):
            mgr = BackupManager(merkaba_dir=tmp_path)
            mgr.run_backup(encrypt=False)

        warning_messages = [r.message for r in caplog.records if r.levelno >= logging.WARNING]
        assert any(
            "unencrypted" in msg.lower() and "not be encrypted at rest" in msg.lower()
            for msg in warning_messages
        ), f"Expected unencrypted warning; got: {warning_messages}"

    def test_encrypted_backup_no_unencrypted_warning(self, tmp_path, caplog):
        """When encryption succeeds, the unencrypted warning should NOT appear."""
        _make_db(tmp_path / "memory.db")

        fake_key = b"A" * 32

        with (
            patch(
                "merkaba.orchestration.backup._get_or_create_backup_key",
                return_value=fake_key,
            ),
            patch(
                "merkaba.orchestration.backup._encrypt_file",
                side_effect=lambda path, key: _fake_encrypt(path),
            ),
            caplog.at_level(logging.WARNING, logger="merkaba.orchestration.backup"),
        ):
            mgr = BackupManager(merkaba_dir=tmp_path)
            mgr.run_backup(encrypt=True)

        warning_messages = [r.message for r in caplog.records if r.levelno >= logging.WARNING]
        assert not any(
            "unencrypted" in msg.lower() and "not be encrypted at rest" in msg.lower()
            for msg in warning_messages
        ), f"Encrypted backup should NOT emit unencrypted warning; got: {warning_messages}"

    def test_encrypt_requested_but_deps_missing_emits_warning(self, tmp_path, caplog):
        """When encrypt=True but deps are missing, BOTH warnings should appear."""
        _make_db(tmp_path / "memory.db")

        with (
            patch(
                "merkaba.orchestration.backup._get_or_create_backup_key",
                side_effect=ImportError("No module named 'cryptography'"),
            ),
            caplog.at_level(logging.WARNING, logger="merkaba.orchestration.backup"),
        ):
            mgr = BackupManager(merkaba_dir=tmp_path)
            mgr.run_backup(encrypt=True)

        warning_messages = [r.message for r in caplog.records if r.levelno >= logging.WARNING]
        # Should have encryption-missing warning
        assert any(
            "encryption" in msg.lower() and "missing" in msg.lower()
            for msg in warning_messages
        ), f"Expected encryption-missing warning; got: {warning_messages}"
        # Should also have unencrypted-at-rest warning
        assert any(
            "unencrypted" in msg.lower() and "not be encrypted at rest" in msg.lower()
            for msg in warning_messages
        ), f"Expected unencrypted-at-rest warning; got: {warning_messages}"


def _fake_encrypt(path: Path) -> Path:
    """Test helper that mimics _encrypt_file without real Fernet."""
    enc_path = path.with_suffix(path.suffix + ".enc")
    enc_path.write_bytes(b"FAKE_ENCRYPTED:" + path.read_bytes())
    path.unlink()
    return enc_path

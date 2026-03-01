# tests/test_cli_security.py
"""Tests for security CLI commands (encryption)."""

import sys
import json
import os
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

# Mock ollama before merkaba imports
_original_ollama = sys.modules.get("ollama")
sys.modules["ollama"] = MagicMock()

from merkaba.cli import app

runner = CliRunner()


@pytest.fixture(autouse=True, scope="module")
def _restore_ollama():
    yield
    if _original_ollama is not None:
        sys.modules["ollama"] = _original_ollama
    else:
        sys.modules.pop("ollama", None)


class TestEnableEncryption:

    def test_enable_encryption_stores_key(self, tmp_path):
        with patch("merkaba.cli.FRIDAY_DIR", str(tmp_path)), \
             patch("merkaba.security.secrets.keyring") as mock_keyring:
            mock_keyring.get_password.return_value = None
            result = runner.invoke(
                app,
                ["security", "enable-encryption"],
                input="my-passphrase\nmy-passphrase\n",
            )
        assert result.exit_code == 0
        assert "enabled" in result.output.lower()
        mock_keyring.set_password.assert_called_once()

    def test_enable_encryption_rejects_mismatch(self, tmp_path):
        with patch("merkaba.cli.FRIDAY_DIR", str(tmp_path)), \
             patch("merkaba.security.secrets.keyring") as mock_keyring:
            mock_keyring.get_password.return_value = None
            result = runner.invoke(
                app,
                ["security", "enable-encryption"],
                input="pass1\npass2\n",
            )
        assert result.exit_code != 0 or "do not match" in result.output.lower()

    def test_enable_encryption_already_configured(self, tmp_path):
        with patch("merkaba.cli.FRIDAY_DIR", str(tmp_path)), \
             patch("merkaba.security.secrets.keyring") as mock_keyring:
            mock_keyring.get_password.return_value = "existing-key"
            result = runner.invoke(app, ["security", "enable-encryption"])
        assert "already" in result.output.lower()

    def test_disable_encryption_removes_key(self, tmp_path):
        with patch("merkaba.cli.FRIDAY_DIR", str(tmp_path)), \
             patch("merkaba.security.secrets.keyring") as mock_keyring:
            mock_keyring.get_password.return_value = "some-key"
            result = runner.invoke(
                app,
                ["security", "disable-encryption", "--yes"],
            )
        assert result.exit_code == 0
        assert "disabled" in result.output.lower()
        mock_keyring.delete_password.assert_called_once()

    def test_disable_encryption_when_not_configured(self, tmp_path):
        with patch("merkaba.cli.FRIDAY_DIR", str(tmp_path)), \
             patch("merkaba.security.secrets.keyring") as mock_keyring:
            mock_keyring.get_password.return_value = None
            result = runner.invoke(app, ["security", "disable-encryption", "--yes"])
        assert "not configured" in result.output.lower()

    def test_encryption_status_shown_in_security_status(self, tmp_path):
        config_path = tmp_path / "config.json"
        config_path.write_text("{}")
        with patch("merkaba.cli.FRIDAY_DIR", str(tmp_path)), \
             patch("merkaba.security.secrets.keyring") as mock_keyring, \
             patch("os.path.expanduser", return_value=str(config_path)):
            mock_keyring.get_password.side_effect = lambda svc, key: "key" if key == "conversation_encryption_key" else None
            result = runner.invoke(app, ["security", "status"])
        assert "encryption" in result.output.lower()

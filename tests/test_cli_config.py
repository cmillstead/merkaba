# tests/test_cli_config.py
import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

# Ensure ollama is mocked before merkaba imports (conftest installs one with proper
# exception classes; setdefault avoids overwriting it).
sys.modules.setdefault("ollama", MagicMock())

from merkaba.cli import app

runner = CliRunner()


class TestConfigShowPrompt:
    def test_show_prompt_displays_resolved(self, tmp_path):
        (tmp_path / "SOUL.md").write_text("My soul")
        (tmp_path / "USER.md").write_text("My user")
        with patch("merkaba.cli.MERKABA_DIR", str(tmp_path)):
            result = runner.invoke(app, ["config", "show-prompt"])
        assert result.exit_code == 0
        assert "My soul" in result.output

    def test_show_prompt_with_business(self, tmp_path):
        biz_dir = tmp_path / "businesses" / "1"
        biz_dir.mkdir(parents=True)
        (biz_dir / "SOUL.md").write_text("Biz soul")
        with patch("merkaba.cli.MERKABA_DIR", str(tmp_path)):
            result = runner.invoke(app, ["config", "show-prompt", "--business", "1"])
        assert result.exit_code == 0
        assert "Biz soul" in result.output

    def test_show_prompt_shows_sources(self, tmp_path):
        (tmp_path / "SOUL.md").write_text("Global")
        with patch("merkaba.cli.MERKABA_DIR", str(tmp_path)):
            result = runner.invoke(app, ["config", "show-prompt"])
        assert "global" in result.output.lower()

    def test_show_prompt_shows_builtin_when_no_files(self, tmp_path):
        with patch("merkaba.cli.MERKABA_DIR", str(tmp_path)):
            result = runner.invoke(app, ["config", "show-prompt"])
        assert result.exit_code == 0
        assert "builtin" in result.output.lower()
        assert "Merkaba" in result.output


class TestConfigEditSoul:
    def test_edit_soul_seeds_default(self, tmp_path):
        with patch("merkaba.cli.MERKABA_DIR", str(tmp_path)), \
             patch("subprocess.run") as mock_run:
            result = runner.invoke(app, ["config", "edit-soul"])
        assert result.exit_code == 0
        assert (tmp_path / "SOUL.md").exists()
        mock_run.assert_called_once()

    def test_edit_soul_business_creates_dir(self, tmp_path):
        with patch("merkaba.cli.MERKABA_DIR", str(tmp_path)), \
             patch("subprocess.run") as mock_run:
            result = runner.invoke(app, ["config", "edit-soul", "--business", "5"])
        assert result.exit_code == 0
        biz_path = tmp_path / "businesses" / "5" / "SOUL.md"
        assert biz_path.exists()


class TestMerkabaHomeOverride:
    """Verify CLI functions respect MERKABA_HOME via load_config()."""

    def test_security_status_reads_config_from_merkaba_home(self, tmp_path):
        """security_status should read config from MERKABA_HOME, not ~/.merkaba."""
        config_data = {
            "security": {
                "totp_threshold": 7,
                "approval_rate_limit": {"max_approvals": 42, "window_seconds": 120},
            }
        }
        (tmp_path / "config.json").write_text(json.dumps(config_data))

        from merkaba.config.loader import clear_cache

        clear_cache()
        with patch.dict(os.environ, {"MERKABA_HOME": str(tmp_path)}), \
             patch("merkaba.security.secrets.get_secret", return_value=None):
            result = runner.invoke(app, ["security", "status"])

        clear_cache()
        assert result.exit_code == 0
        assert "42" in result.output
        assert "120" in result.output
        assert ">= 7" in result.output

    def test_security_migrate_keys_reads_config_from_merkaba_home(self, tmp_path):
        """security_migrate_keys should read config from MERKABA_HOME."""
        config_data = {
            "cloud_providers": {
                "openai": {"api_key": "sk-test-key-123"}
            }
        }
        (tmp_path / "config.json").write_text(json.dumps(config_data))

        from merkaba.config.loader import clear_cache

        clear_cache()
        mock_keyring = MagicMock()
        with patch.dict(os.environ, {"MERKABA_HOME": str(tmp_path)}), \
             patch.dict(sys.modules, {"keyring": mock_keyring}):
            result = runner.invoke(app, ["security", "migrate-keys"], input="n\n")

        clear_cache()
        assert result.exit_code == 0
        mock_keyring.set_password.assert_called_once_with(
            "merkaba", "openai_api_key", "sk-test-key-123"
        )
        assert "openai" in result.output


class TestConfigEditUser:
    def test_edit_user_seeds_default(self, tmp_path):
        with patch("merkaba.cli.MERKABA_DIR", str(tmp_path)), \
             patch("subprocess.run") as mock_run:
            result = runner.invoke(app, ["config", "edit-user"])
        assert result.exit_code == 0
        assert (tmp_path / "USER.md").exists()
        mock_run.assert_called_once()

    def test_edit_user_business_creates_dir(self, tmp_path):
        with patch("merkaba.cli.MERKABA_DIR", str(tmp_path)), \
             patch("subprocess.run") as mock_run:
            result = runner.invoke(app, ["config", "edit-user", "--business", "3"])
        assert result.exit_code == 0
        biz_path = tmp_path / "businesses" / "3" / "USER.md"
        assert biz_path.exists()

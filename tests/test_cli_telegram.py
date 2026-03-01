# tests/test_cli_telegram.py
"""Tests for Telegram CLI commands."""

import pytest
from typer.testing import CliRunner
from unittest.mock import patch, MagicMock

# Check if required dependencies are available
try:
    from merkaba.cli import app
    HAS_DEPENDENCIES = True
except ImportError as e:
    HAS_DEPENDENCIES = False
    IMPORT_ERROR = str(e)
    app = None

runner = CliRunner()

pytestmark = pytest.mark.skipif(
    not HAS_DEPENDENCIES,
    reason=f"Missing required dependencies: {IMPORT_ERROR if not HAS_DEPENDENCIES else ''}"
)


class TestTelegramSetupCommand:
    """Tests for merkaba telegram setup command."""

    @patch("merkaba.telegram.TelegramConfig")
    def test_telegram_setup_saves_config(self, mock_config):
        """telegram setup should save bot token and user ID."""
        mock_config_instance = MagicMock()
        mock_config.return_value = mock_config_instance

        result = runner.invoke(
            app,
            ["telegram", "setup"],
            input="123:ABC-token\n987654321\n"
        )

        assert result.exit_code == 0
        mock_config_instance.save_bot_token.assert_called_once_with("123:ABC-token")
        mock_config_instance.save_allowed_user_ids.assert_called_once_with([987654321])

    @patch("merkaba.telegram.TelegramConfig")
    def test_telegram_setup_shows_success(self, mock_config):
        """telegram setup should show success message."""
        mock_config.return_value = MagicMock()

        result = runner.invoke(
            app,
            ["telegram", "setup"],
            input="123:ABC\n12345\n"
        )

        assert "saved" in result.output.lower() or "configured" in result.output.lower()


class TestTelegramStatusCommand:
    """Tests for merkaba telegram status command."""

    @patch("merkaba.telegram.TelegramConfig")
    def test_telegram_status_not_configured(self, mock_config):
        """telegram status should show not configured when missing."""
        mock_config_instance = MagicMock()
        mock_config_instance.is_configured.return_value = False
        mock_config.return_value = mock_config_instance

        result = runner.invoke(app, ["telegram", "status"])

        assert "not configured" in result.output.lower()

    @patch("merkaba.telegram.TelegramConfig")
    def test_telegram_status_configured(self, mock_config):
        """telegram status should show configured when set up."""
        mock_config_instance = MagicMock()
        mock_config_instance.is_configured.return_value = True
        mock_config_instance.get_allowed_user_ids.return_value = [123]
        mock_config.return_value = mock_config_instance

        result = runner.invoke(app, ["telegram", "status"])

        assert "configured" in result.output.lower()


class TestServeCommand:
    """Tests for merkaba serve command."""

    @patch("merkaba.telegram.TelegramConfig")
    def test_serve_requires_telegram_config(self, mock_config):
        """serve should fail if telegram not configured."""
        mock_config_instance = MagicMock()
        mock_config_instance.is_configured.return_value = False
        mock_config.return_value = mock_config_instance

        result = runner.invoke(app, ["serve"])

        assert result.exit_code != 0
        assert "telegram" in result.output.lower()

    @patch("merkaba.telegram.MerkabaBot")
    @patch("merkaba.telegram.TelegramConfig")
    def test_serve_starts_bot(self, mock_config, mock_bot):
        """serve should start the bot when configured."""
        mock_config_instance = MagicMock()
        mock_config_instance.is_configured.return_value = True
        mock_config_instance.get_bot_token.return_value = "token"
        mock_config_instance.get_allowed_user_ids.return_value = [123]
        mock_config.return_value = mock_config_instance

        mock_bot_instance = MagicMock()
        mock_bot.return_value = mock_bot_instance

        result = runner.invoke(app, ["serve"])

        mock_bot.assert_called_once()

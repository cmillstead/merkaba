# tests/test_telegram_commands.py
"""Tests for Telegram command handlers."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# Check if required dependencies are available
try:
    from merkaba.telegram import commands as telegram_commands
    HAS_DEPENDENCIES = True
except ImportError as e:
    HAS_DEPENDENCIES = False
    IMPORT_ERROR = str(e)
    telegram_commands = None

pytestmark = pytest.mark.skipif(
    not HAS_DEPENDENCIES,
    reason=f"Missing required dependencies: {IMPORT_ERROR if not HAS_DEPENDENCIES else ''}"
)


class TestResearchCommand:
    """Tests for /research command."""

    @pytest.mark.asyncio
    @patch("merkaba.telegram.commands.ApifyClient")
    @patch("merkaba.telegram.commands.analyze_listings")
    async def test_research_command_runs_search(self, mock_analyze, mock_client):
        """research command should run Etsy search."""
        from merkaba.telegram.commands import handle_research

        mock_client_instance = MagicMock()
        mock_client_instance.search_etsy.return_value = [{"title": "Test"}]
        mock_client.return_value = mock_client_instance
        mock_analyze.return_value = {"opportunity_score": 75.0}

        mock_update = MagicMock()
        mock_update.effective_user.id = 123
        mock_update.message.reply_text = AsyncMock()
        mock_context = MagicMock()
        mock_context.args = ["boho", "clipart"]

        await handle_research(mock_update, mock_context)

        mock_client_instance.search_etsy.assert_called_once()
        # Should send at least a completion message
        assert mock_update.message.reply_text.called

    @pytest.mark.asyncio
    async def test_research_command_requires_query(self):
        """research command should require a search query."""
        from merkaba.telegram.commands import handle_research

        mock_update = MagicMock()
        mock_update.message.reply_text = AsyncMock()
        mock_context = MagicMock()
        mock_context.args = []

        await handle_research(mock_update, mock_context)

        call_args = mock_update.message.reply_text.call_args[0][0]
        assert "usage" in call_args.lower() or "query" in call_args.lower()


class TestListingCommands:
    """Tests for /listing commands."""

    @pytest.mark.asyncio
    @patch("merkaba.telegram.commands.ListingConfig")
    async def test_listing_auth_status(self, mock_config):
        """listing auth should check auth status."""
        from merkaba.telegram.commands import handle_listing

        mock_config_instance = MagicMock()
        mock_config_instance.get_tokens.return_value = None
        mock_config.return_value = mock_config_instance

        mock_update = MagicMock()
        mock_update.message.reply_text = AsyncMock()
        mock_context = MagicMock()
        mock_context.args = ["auth"]

        await handle_listing(mock_update, mock_context)

        call_args = mock_update.message.reply_text.call_args[0][0]
        assert "auth" in call_args.lower()

    @pytest.mark.asyncio
    @patch("merkaba.telegram.commands.EtsyClient")
    @patch("merkaba.telegram.commands.ListingConfig")
    async def test_listing_list_shows_listings(self, mock_config, mock_client):
        """listing list should show shop listings."""
        from merkaba.telegram.commands import handle_listing

        mock_config_instance = MagicMock()
        mock_config_instance.get_tokens.return_value = {"access_token": "test"}
        mock_config_instance.is_token_expired.return_value = False
        mock_config_instance.get_shop_id.return_value = "123"
        mock_config.return_value = mock_config_instance

        mock_client_instance = MagicMock()
        mock_client_instance.list_listings.return_value = [
            {"listing_id": 1, "title": "Test", "state": "draft"}
        ]
        mock_client.return_value = mock_client_instance

        mock_update = MagicMock()
        mock_update.message.reply_text = AsyncMock()
        mock_context = MagicMock()
        mock_context.args = ["list"]

        await handle_listing(mock_update, mock_context)

        assert mock_update.message.reply_text.called

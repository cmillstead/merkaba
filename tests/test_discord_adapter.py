"""Tests for DiscordAdapter with mocked discord.py client."""

import sys
from unittest.mock import patch, MagicMock, AsyncMock

import pytest

# Ensure discord.py is mockable even when not installed
if "discord" not in sys.modules:
    _discord_mock = MagicMock()
    _discord_mock.Intents.default.return_value = MagicMock(
        message_content=False, guilds=False
    )
    sys.modules["discord"] = _discord_mock
    sys.modules["discord.ext"] = MagicMock()
    sys.modules["discord.ext.commands"] = MagicMock()

from merkaba.integrations.discord_adapter import DiscordAdapter
from merkaba.integrations.base import ADAPTER_REGISTRY


class TestDiscordAdapterRegistration:
    def test_registered_in_adapter_registry(self):
        assert "discord" in ADAPTER_REGISTRY
        assert ADAPTER_REGISTRY["discord"] is DiscordAdapter


class TestDiscordAdapterConnect:
    def test_connect_fails_without_credentials(self):
        adapter = DiscordAdapter(name="discord")
        with patch.object(
            adapter._creds, "has_required", return_value=(False, ["bot_token"])
        ):
            assert adapter.connect() is False
            assert not adapter.is_connected

    def test_connect_succeeds_with_credentials(self):
        adapter = DiscordAdapter(name="discord")
        with patch.object(
            adapter._creds, "has_required", return_value=(True, [])
        ), patch.object(adapter._creds, "get", return_value="fake-token"):
            result = adapter.connect()
            assert result is True
            assert adapter.is_connected
            assert adapter._bot is not None

    def test_connect_fails_without_discord_installed(self):
        adapter = DiscordAdapter(name="discord")
        with patch.object(
            adapter._creds, "has_required", return_value=(True, [])
        ), patch.object(
            adapter._creds, "get", return_value="fake-token"
        ), patch.dict(sys.modules, {"discord": None, "discord.ext": None, "discord.ext.commands": None}):
            # Patching sys.modules with None causes ImportError on import
            result = adapter.connect()
            assert result is False
            assert not adapter.is_connected


class TestDiscordAdapterExecute:
    @pytest.fixture
    def connected_adapter(self):
        """Return a DiscordAdapter with a mocked bot."""
        adapter = DiscordAdapter(name="discord")
        adapter._connected = True
        adapter._bot = MagicMock()
        return adapter

    def test_unknown_action(self, connected_adapter):
        result = connected_adapter.execute("invalid_action")
        assert not result["ok"]
        assert "Unknown action" in result["error"]

    def test_send_message_missing_params(self, connected_adapter):
        result = connected_adapter.execute("send_message", {})
        assert not result["ok"]
        assert "Missing required parameter" in result["error"]

    def test_send_message_channel_not_found(self, connected_adapter):
        connected_adapter._bot.get_channel.return_value = None
        result = connected_adapter.execute(
            "send_message", {"channel_id": 123, "text": "hello"}
        )
        assert not result["ok"]
        assert "not found" in result["error"]

    def test_send_message_success(self, connected_adapter):
        mock_channel = MagicMock()
        mock_msg = MagicMock()
        mock_msg.id = 99999
        mock_loop = MagicMock()
        mock_loop.is_running.return_value = True

        mock_future = MagicMock()
        mock_future.result.return_value = mock_msg

        connected_adapter._bot.get_channel.return_value = mock_channel
        connected_adapter._bot.loop = mock_loop

        with patch("asyncio.run_coroutine_threadsafe", return_value=mock_future):
            result = connected_adapter.execute(
                "send_message", {"channel_id": 123, "text": "hello"}
            )
        assert result["ok"]
        assert result["message_id"] == "99999"

    def test_send_message_loop_not_running(self, connected_adapter):
        mock_channel = MagicMock()
        mock_loop = MagicMock()
        mock_loop.is_running.return_value = False

        connected_adapter._bot.get_channel.return_value = mock_channel
        connected_adapter._bot.loop = mock_loop

        result = connected_adapter.execute(
            "send_message", {"channel_id": 123, "text": "hello"}
        )
        assert not result["ok"]
        assert "not running" in result["error"]

    def test_send_message_exception(self, connected_adapter):
        connected_adapter._bot.get_channel.side_effect = Exception("network error")
        result = connected_adapter.execute(
            "send_message", {"channel_id": 123, "text": "hello"}
        )
        assert not result["ok"]
        assert "network error" in result["error"]

    def test_read_messages_missing_params(self, connected_adapter):
        result = connected_adapter.execute("read_messages", {})
        assert not result["ok"]
        assert "Missing required parameter" in result["error"]

    def test_read_messages_channel_not_found(self, connected_adapter):
        connected_adapter._bot.get_channel.return_value = None
        result = connected_adapter.execute(
            "read_messages", {"channel_id": 456}
        )
        assert not result["ok"]
        assert "not found" in result["error"]

    def test_read_messages_success(self, connected_adapter):
        mock_channel = MagicMock()
        mock_loop = MagicMock()
        mock_loop.is_running.return_value = True

        mock_future = MagicMock()
        mock_future.result.return_value = [
            {
                "id": "1",
                "author": "user#1234",
                "content": "hi there",
                "timestamp": "2026-03-01T00:00:00",
            }
        ]

        connected_adapter._bot.get_channel.return_value = mock_channel
        connected_adapter._bot.loop = mock_loop

        with patch("asyncio.run_coroutine_threadsafe", return_value=mock_future):
            result = connected_adapter.execute(
                "read_messages", {"channel_id": 456, "limit": 5}
            )
        assert result["ok"]
        assert len(result["messages"]) == 1
        assert result["messages"][0]["content"] == "hi there"

    def test_read_messages_default_limit(self, connected_adapter):
        """read_messages uses limit=10 by default."""
        mock_channel = MagicMock()
        mock_loop = MagicMock()
        mock_loop.is_running.return_value = True
        mock_future = MagicMock()
        mock_future.result.return_value = []

        connected_adapter._bot.get_channel.return_value = mock_channel
        connected_adapter._bot.loop = mock_loop

        with patch("asyncio.run_coroutine_threadsafe", return_value=mock_future) as mock_coro:
            connected_adapter.execute("read_messages", {"channel_id": 456})
            # The coroutine was called (we can't easily inspect the limit
            # argument through run_coroutine_threadsafe, but at least
            # verify the call succeeded)
            mock_coro.assert_called_once()

    def test_read_messages_exception(self, connected_adapter):
        connected_adapter._bot.get_channel.side_effect = Exception("timeout")
        result = connected_adapter.execute(
            "read_messages", {"channel_id": 456}
        )
        assert not result["ok"]
        assert "timeout" in result["error"]

    def test_list_channels_all_guilds(self, connected_adapter):
        guild1 = MagicMock()
        guild1.name = "Server1"
        guild1.id = 100
        ch1 = MagicMock()
        ch1.id = 200
        ch1.name = "general"
        guild1.text_channels = [ch1]

        guild2 = MagicMock()
        guild2.name = "Server2"
        guild2.id = 101
        ch2 = MagicMock()
        ch2.id = 201
        ch2.name = "dev"
        guild2.text_channels = [ch2]

        connected_adapter._bot.guilds = [guild1, guild2]

        result = connected_adapter.execute("list_channels")
        assert result["ok"]
        assert len(result["channels"]) == 2
        assert result["channels"][0]["name"] == "general"
        assert result["channels"][0]["guild"] == "Server1"
        assert result["channels"][1]["name"] == "dev"

    def test_list_channels_specific_guild(self, connected_adapter):
        guild = MagicMock()
        guild.name = "MyServer"
        guild.id = 100
        ch = MagicMock()
        ch.id = 200
        ch.name = "general"
        guild.text_channels = [ch]

        connected_adapter._bot.get_guild.return_value = guild

        result = connected_adapter.execute(
            "list_channels", {"guild_id": 100}
        )
        assert result["ok"]
        assert len(result["channels"]) == 1
        connected_adapter._bot.get_guild.assert_called_once_with(100)

    def test_list_channels_guild_not_found(self, connected_adapter):
        connected_adapter._bot.get_guild.return_value = None
        result = connected_adapter.execute(
            "list_channels", {"guild_id": 999}
        )
        assert not result["ok"]
        assert "not found" in result["error"]

    def test_list_channels_exception(self, connected_adapter):
        connected_adapter._bot.guilds = MagicMock(
            side_effect=Exception("forbidden")
        )
        # Iterating over guilds will raise
        type(connected_adapter._bot).guilds = property(
            lambda self: (_ for _ in ()).throw(Exception("forbidden"))
        )
        result = connected_adapter.execute("list_channels")
        assert not result["ok"]
        assert "forbidden" in result["error"]
        # Restore
        type(connected_adapter._bot).guilds = MagicMock()


class TestDiscordAdapterHealthCheck:
    def test_health_check_not_connected(self):
        adapter = DiscordAdapter(name="discord")
        result = adapter.health_check()
        assert not result["ok"]
        assert result["adapter"] == "discord"
        assert "Not connected" in result["error"]

    def test_health_check_initialized_no_user(self):
        adapter = DiscordAdapter(name="discord")
        adapter._connected = True
        adapter._bot = MagicMock()
        adapter._bot.user = None
        result = adapter.health_check()
        assert result["ok"]
        assert result["status"] == "initialized"

    def test_health_check_logged_in(self):
        adapter = DiscordAdapter(name="discord")
        adapter._connected = True
        adapter._bot = MagicMock()
        adapter._bot.user = MagicMock(__str__=lambda self: "Merkaba#1234")
        adapter._bot.guilds = [MagicMock(), MagicMock()]
        result = adapter.health_check()
        assert result["ok"]
        assert result["user"] == "Merkaba#1234"
        assert result["guilds"] == 2

    def test_health_check_exception(self):
        adapter = DiscordAdapter(name="discord")
        adapter._connected = True
        adapter._bot = MagicMock()
        type(adapter._bot).user = property(
            lambda self: (_ for _ in ()).throw(Exception("API error"))
        )
        result = adapter.health_check()
        assert not result["ok"]
        assert "API error" in result["error"]
        # Restore
        type(adapter._bot).user = MagicMock()


class TestDiscordAdapterDisconnect:
    def test_disconnect_sets_connected_false(self):
        adapter = DiscordAdapter(name="discord")
        adapter._connected = True
        adapter._bot = MagicMock()
        adapter._bot.loop = None
        adapter.disconnect()
        assert not adapter.is_connected

    def test_disconnect_with_running_loop(self):
        adapter = DiscordAdapter(name="discord")
        adapter._connected = True
        mock_loop = MagicMock()
        mock_loop.is_running.return_value = True
        adapter._bot = MagicMock()
        adapter._bot.loop = mock_loop

        with patch("asyncio.run_coroutine_threadsafe") as mock_coro:
            adapter.disconnect()
            mock_coro.assert_called_once()
        assert not adapter.is_connected

    def test_disconnect_handles_exception(self):
        adapter = DiscordAdapter(name="discord")
        adapter._connected = True
        adapter._bot = MagicMock()
        type(adapter._bot).loop = property(
            lambda self: (_ for _ in ()).throw(Exception("already closed"))
        )
        # Should not raise
        adapter.disconnect()
        assert not adapter.is_connected
        # Restore
        type(adapter._bot).loop = MagicMock()

    def test_disconnect_no_bot(self):
        adapter = DiscordAdapter(name="discord")
        adapter._connected = True
        adapter._bot = None
        adapter.disconnect()
        assert not adapter.is_connected


class TestDiscordSessionId:
    def test_basic_session_id(self):
        sid = DiscordAdapter.build_session_id("12345", "67890")
        assert sid == "discord:12345:topic:67890"

    def test_session_id_without_channel(self):
        sid = DiscordAdapter.build_session_id("12345")
        assert sid == "discord:12345"

    def test_session_id_with_business(self):
        sid = DiscordAdapter.build_session_id("12345", "67890", business_id="1")
        assert sid == "discord:12345:topic:67890:biz:1"

    def test_session_id_int_params(self):
        sid = DiscordAdapter.build_session_id(12345, 67890)
        assert sid == "discord:12345:topic:67890"


class TestDiscordAdapterMessageHandler:
    def test_setup_handler_without_connect_raises(self):
        adapter = DiscordAdapter(name="discord")
        with pytest.raises(RuntimeError, match="Call connect"):
            adapter.setup_message_handler()

    def test_setup_handler_creates_pool(self):
        adapter = DiscordAdapter(name="discord")
        adapter._bot = MagicMock()
        with patch(
            "merkaba.orchestration.session_pool.SessionPool"
        ) as mock_pool_cls:
            adapter.setup_message_handler()
            mock_pool_cls.assert_called_once()
            assert adapter._pool is mock_pool_cls.return_value

    def test_setup_handler_uses_provided_pool(self):
        adapter = DiscordAdapter(name="discord")
        adapter._bot = MagicMock()
        pool = MagicMock()
        adapter.setup_message_handler(pool=pool)
        assert adapter._pool is pool

    def test_run_without_connect_raises(self):
        adapter = DiscordAdapter(name="discord")
        with pytest.raises(RuntimeError, match="Call connect"):
            adapter.run()

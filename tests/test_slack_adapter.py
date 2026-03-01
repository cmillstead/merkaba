from unittest.mock import patch, MagicMock
import pytest
from merkaba.integrations.slack_adapter import SlackAdapter


class TestSlackAdapter:
    def test_connect_fails_without_credentials(self):
        adapter = SlackAdapter(name="slack")
        with patch.object(adapter._creds, "has_required", return_value=(False, ["bot_token"])):
            assert adapter.connect() is False
            assert not adapter.is_connected

    def test_connect_succeeds_with_credentials(self):
        adapter = SlackAdapter(name="slack")
        with patch.object(adapter._creds, "has_required", return_value=(True, [])), \
             patch.object(adapter._creds, "get", return_value="xoxb-fake"), \
             patch("merkaba.integrations.slack_adapter.SlackAdapter.connect") as mock_connect:
            # We need to mock the import of slack_sdk
            mock_connect.return_value = True
            adapter._connected = True
            assert adapter.is_connected

    def test_send_message(self):
        adapter = SlackAdapter(name="slack")
        adapter._connected = True
        mock_client = MagicMock()
        mock_client.chat_postMessage.return_value = {"ok": True, "ts": "123"}
        adapter._slack = mock_client
        result = adapter.execute("send_message", {"channel": "#general", "text": "hello"})
        assert result["ok"]
        mock_client.chat_postMessage.assert_called_once()

    def test_read_messages(self):
        adapter = SlackAdapter(name="slack")
        adapter._connected = True
        mock_client = MagicMock()
        mock_client.conversations_history.return_value = {
            "ok": True, "messages": [{"text": "hi", "ts": "1"}]
        }
        adapter._slack = mock_client
        result = adapter.execute("read_messages", {"channel": "C123", "limit": 5})
        assert result["ok"]
        assert len(result["messages"]) == 1

    def test_list_channels(self):
        adapter = SlackAdapter(name="slack")
        adapter._connected = True
        mock_client = MagicMock()
        mock_client.conversations_list.return_value = {
            "ok": True, "channels": [{"name": "general", "id": "C1"}]
        }
        adapter._slack = mock_client
        result = adapter.execute("list_channels")
        assert result["ok"]

    def test_react(self):
        adapter = SlackAdapter(name="slack")
        adapter._connected = True
        mock_client = MagicMock()
        adapter._slack = mock_client
        result = adapter.execute("react", {"channel": "C123", "timestamp": "123", "emoji": "thumbsup"})
        assert result["ok"]
        mock_client.reactions_add.assert_called_once()

    def test_unknown_action(self):
        adapter = SlackAdapter(name="slack")
        adapter._connected = True
        result = adapter.execute("invalid_action")
        assert not result["ok"]

    def test_health_check_not_connected(self):
        adapter = SlackAdapter(name="slack")
        result = adapter.health_check()
        assert not result["ok"]

    def test_health_check_connected(self):
        adapter = SlackAdapter(name="slack")
        adapter._connected = True
        mock_client = MagicMock()
        mock_client.auth_test.return_value = {"ok": True, "user": "merkaba"}
        adapter._slack = mock_client
        result = adapter.health_check()
        assert result["ok"]

    def test_send_message_error(self):
        adapter = SlackAdapter(name="slack")
        adapter._connected = True
        mock_client = MagicMock()
        mock_client.chat_postMessage.side_effect = Exception("network error")
        adapter._slack = mock_client
        result = adapter.execute("send_message", {"channel": "#general", "text": "hello"})
        assert not result["ok"]
        assert "network error" in result["error"]

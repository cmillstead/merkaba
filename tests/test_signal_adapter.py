"""Tests for Signal integration adapter via signal-cli JSON-RPC."""

import json
from unittest.mock import patch, MagicMock

import pytest
from merkaba.integrations.signal_adapter import SignalAdapter, _build_session_id


class TestSignalSessionId:
    def test_phone_number_session_id(self):
        sid = _build_session_id("+15551234567")
        assert sid == "signal:+15551234567"

    def test_group_id_session_id(self):
        sid = _build_session_id("group123abc")
        assert sid == "signal:group123abc"


class TestSignalAdapterConnect:
    def test_connect_fails_without_credentials(self):
        adapter = SignalAdapter(name="signal")
        with patch.object(adapter._creds, "has_required", return_value=(False, ["account"])):
            assert adapter.connect() is False
            assert not adapter.is_connected

    def test_connect_fails_without_binary(self):
        adapter = SignalAdapter(name="signal")
        with (
            patch.object(adapter._creds, "has_required", return_value=(True, [])),
            patch.object(adapter._creds, "get", return_value="+15551234567"),
            patch("shutil.which", return_value=None),
        ):
            assert adapter.connect() is False
            assert not adapter.is_connected

    def test_connect_succeeds(self):
        adapter = SignalAdapter(name="signal")
        with (
            patch.object(adapter._creds, "has_required", return_value=(True, [])),
            patch.object(adapter._creds, "get", return_value="+15551234567"),
            patch("shutil.which", return_value="/usr/local/bin/signal-cli"),
        ):
            assert adapter.connect() is True
            assert adapter.is_connected
            assert adapter._account == "+15551234567"

    def test_connect_custom_cli_path(self):
        adapter = SignalAdapter(name="signal")

        def fake_get(adapter_name, key):
            return {
                "account": "+15551234567",
                "signal_cli_path": "/opt/bin/signal-cli",
            }.get(key)

        with (
            patch.object(adapter._creds, "has_required", return_value=(True, [])),
            patch.object(adapter._creds, "get", side_effect=fake_get),
            patch("shutil.which", return_value="/opt/bin/signal-cli"),
        ):
            assert adapter.connect() is True
            assert adapter._signal_cli == "/opt/bin/signal-cli"


class TestSignalAdapterDisconnect:
    def test_disconnect(self):
        adapter = SignalAdapter(name="signal")
        adapter._connected = True
        adapter._account = "+15551234567"
        adapter.disconnect()
        assert not adapter.is_connected
        assert adapter._account is None


class TestSignalAdapterHealthCheck:
    def test_health_check_not_connected(self):
        adapter = SignalAdapter(name="signal")
        result = adapter.health_check()
        assert not result["ok"]
        assert result["adapter"] == "signal"

    def test_health_check_registered(self):
        adapter = SignalAdapter(name="signal")
        adapter._connected = True
        adapter._account = "+15551234567"

        rpc_response = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": [{"number": "+15551234567"}],
        }

        with patch.object(adapter, "_jsonrpc", return_value=rpc_response):
            result = adapter.health_check()
            assert result["ok"]
            assert result["adapter"] == "signal"
            assert result["account"] == "+15551234567"
            assert result["registered"] is True

    def test_health_check_not_registered(self):
        adapter = SignalAdapter(name="signal")
        adapter._connected = True
        adapter._account = "+15551234567"

        rpc_response = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": [{"number": "+19998887777"}],
        }

        with patch.object(adapter, "_jsonrpc", return_value=rpc_response):
            result = adapter.health_check()
            assert not result["ok"]
            assert result["registered"] is False

    def test_health_check_error(self):
        adapter = SignalAdapter(name="signal")
        adapter._connected = True
        adapter._account = "+15551234567"

        with patch.object(adapter, "_jsonrpc", side_effect=RuntimeError("signal-cli not running")):
            result = adapter.health_check()
            assert not result["ok"]
            assert "signal-cli not running" in result["error"]


class TestSignalAdapterSendMessage:
    def _make_adapter(self):
        adapter = SignalAdapter(name="signal")
        adapter._connected = True
        adapter._account = "+15551234567"
        return adapter

    def test_send_message_to_individual(self):
        adapter = self._make_adapter()
        rpc_response = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"timestamp": 1709300000000},
        }

        with patch.object(adapter, "_jsonrpc", return_value=rpc_response) as mock_rpc:
            result = adapter.execute(
                "send_message",
                {"recipient": "+19998887777", "text": "Hello from Merkaba"},
            )
            assert result["ok"]
            assert result["session_id"] == "signal:+19998887777"
            assert result["timestamp"] == 1709300000000

            mock_rpc.assert_called_once_with(
                "send",
                {
                    "message": "Hello from Merkaba",
                    "recipient": ["+19998887777"],
                },
            )

    def test_send_message_to_group(self):
        adapter = self._make_adapter()
        rpc_response = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"timestamp": 1709300000000},
        }

        with patch.object(adapter, "_jsonrpc", return_value=rpc_response) as mock_rpc:
            result = adapter.execute(
                "send_message",
                {"recipient": "groupABC123", "text": "Hello group", "group": True},
            )
            assert result["ok"]
            assert result["session_id"] == "signal:groupABC123"

            mock_rpc.assert_called_once_with(
                "send",
                {
                    "message": "Hello group",
                    "groupId": "groupABC123",
                },
            )

    def test_send_message_missing_params(self):
        adapter = self._make_adapter()
        result = adapter.execute("send_message", {"text": "no recipient"})
        assert not result["ok"]
        assert "recipient" in result["error"]

    def test_send_message_missing_text(self):
        adapter = self._make_adapter()
        result = adapter.execute("send_message", {"recipient": "+19998887777"})
        assert not result["ok"]
        assert "text" in result["error"]

    def test_send_message_error(self):
        adapter = self._make_adapter()
        with patch.object(adapter, "_jsonrpc", side_effect=RuntimeError("send failed")):
            result = adapter.execute(
                "send_message",
                {"recipient": "+19998887777", "text": "fail"},
            )
            assert not result["ok"]
            assert "send failed" in result["error"]


class TestSignalAdapterReadMessages:
    def _make_adapter(self):
        adapter = SignalAdapter(name="signal")
        adapter._connected = True
        adapter._account = "+15551234567"
        return adapter

    def test_read_messages_individual(self):
        adapter = self._make_adapter()
        rpc_response = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": [
                {
                    "source": "+19998887777",
                    "dataMessage": {
                        "message": "Hi there!",
                        "timestamp": 1709300000001,
                    },
                },
            ],
        }

        with patch.object(adapter, "_jsonrpc", return_value=rpc_response):
            result = adapter.execute("read_messages", {"timeout": 2})
            assert result["ok"]
            assert len(result["messages"]) == 1
            msg = result["messages"][0]
            assert msg["source"] == "+19998887777"
            assert msg["text"] == "Hi there!"
            assert msg["session_id"] == "signal:+19998887777"
            assert msg["group_id"] is None

    def test_read_messages_group(self):
        adapter = self._make_adapter()
        rpc_response = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": [
                {
                    "source": "+19998887777",
                    "dataMessage": {
                        "message": "Group message",
                        "timestamp": 1709300000002,
                        "groupInfo": {"groupId": "groupABC123"},
                    },
                },
            ],
        }

        with patch.object(adapter, "_jsonrpc", return_value=rpc_response):
            result = adapter.execute("read_messages")
            assert result["ok"]
            msg = result["messages"][0]
            assert msg["group_id"] == "groupABC123"
            assert msg["session_id"] == "signal:groupABC123"

    def test_read_messages_empty(self):
        adapter = self._make_adapter()
        rpc_response = {"jsonrpc": "2.0", "id": 1, "result": []}

        with patch.object(adapter, "_jsonrpc", return_value=rpc_response):
            result = adapter.execute("read_messages")
            assert result["ok"]
            assert result["messages"] == []

    def test_read_messages_error(self):
        adapter = self._make_adapter()
        with patch.object(adapter, "_jsonrpc", side_effect=RuntimeError("timeout")):
            result = adapter.execute("read_messages")
            assert not result["ok"]
            assert "timeout" in result["error"]

    def test_read_messages_envelope_format(self):
        """Test handling of nested envelope format from signal-cli."""
        adapter = self._make_adapter()
        rpc_response = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": [
                {
                    "envelope": {
                        "source": "+19998887777",
                        "dataMessage": {
                            "message": "Nested format",
                            "timestamp": 1709300000003,
                        },
                    },
                },
            ],
        }

        with patch.object(adapter, "_jsonrpc", return_value=rpc_response):
            result = adapter.execute("read_messages")
            assert result["ok"]
            msg = result["messages"][0]
            assert msg["text"] == "Nested format"
            assert msg["source"] == "+19998887777"


class TestSignalAdapterListGroups:
    def _make_adapter(self):
        adapter = SignalAdapter(name="signal")
        adapter._connected = True
        adapter._account = "+15551234567"
        return adapter

    def test_list_groups(self):
        adapter = self._make_adapter()
        rpc_response = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": [
                {"id": "grp1", "name": "Family", "members": ["+1111", "+2222"]},
                {"id": "grp2", "name": "Work", "members": ["+3333"]},
            ],
        }

        with patch.object(adapter, "_jsonrpc", return_value=rpc_response):
            result = adapter.execute("list_groups")
            assert result["ok"]
            assert len(result["groups"]) == 2
            assert result["groups"][0]["name"] == "Family"
            assert result["groups"][1]["members"] == ["+3333"]

    def test_list_groups_error(self):
        adapter = self._make_adapter()
        with patch.object(adapter, "_jsonrpc", side_effect=RuntimeError("rpc fail")):
            result = adapter.execute("list_groups")
            assert not result["ok"]


class TestSignalAdapterGetContacts:
    def _make_adapter(self):
        adapter = SignalAdapter(name="signal")
        adapter._connected = True
        adapter._account = "+15551234567"
        return adapter

    def test_get_contacts(self):
        adapter = self._make_adapter()
        rpc_response = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": [
                {"number": "+19998887777", "name": "Alice", "profileName": "alice123"},
                {"number": "+18887776666", "name": "Bob", "profileName": "bobby"},
            ],
        }

        with patch.object(adapter, "_jsonrpc", return_value=rpc_response):
            result = adapter.execute("get_contacts")
            assert result["ok"]
            assert len(result["contacts"]) == 2
            assert result["contacts"][0]["number"] == "+19998887777"
            assert result["contacts"][1]["profile_name"] == "bobby"

    def test_get_contacts_error(self):
        adapter = self._make_adapter()
        with patch.object(adapter, "_jsonrpc", side_effect=RuntimeError("contact fail")):
            result = adapter.execute("get_contacts")
            assert not result["ok"]


class TestSignalAdapterUnknownAction:
    def test_unknown_action(self):
        adapter = SignalAdapter(name="signal")
        adapter._connected = True
        result = adapter.execute("invalid_action")
        assert not result["ok"]
        assert "Unknown action" in result["error"]


class TestSignalAdapterJsonRpc:
    def _make_adapter(self):
        adapter = SignalAdapter(name="signal")
        adapter._connected = True
        adapter._account = "+15551234567"
        return adapter

    def test_jsonrpc_success(self):
        adapter = self._make_adapter()
        rpc_response = json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"ok": True}})
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = rpc_response + "\n"
        mock_proc.stderr = ""

        with patch("subprocess.run", return_value=mock_proc) as mock_run:
            result = adapter._jsonrpc("testMethod", {"key": "val"})
            assert result["result"] == {"ok": True}

            call_args = mock_run.call_args
            assert call_args[0][0] == ["signal-cli", "--output=json", "jsonRpc"]
            input_data = json.loads(call_args[1]["input"].strip())
            assert input_data["method"] == "testMethod"
            assert input_data["params"]["key"] == "val"
            assert input_data["params"]["account"] == "+15551234567"

    def test_jsonrpc_nonzero_exit(self):
        adapter = self._make_adapter()
        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.stdout = ""
        mock_proc.stderr = "signal-cli: command not found"

        with patch("subprocess.run", return_value=mock_proc):
            with pytest.raises(RuntimeError, match="signal-cli error"):
                adapter._jsonrpc("testMethod")

    def test_jsonrpc_empty_output(self):
        adapter = self._make_adapter()
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = ""
        mock_proc.stderr = ""

        with patch("subprocess.run", return_value=mock_proc):
            with pytest.raises(RuntimeError, match="no output"):
                adapter._jsonrpc("testMethod")

    def test_jsonrpc_error_response(self):
        adapter = self._make_adapter()
        rpc_response = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "error": {"code": -32601, "message": "Method not found"},
        })
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = rpc_response + "\n"
        mock_proc.stderr = ""

        with patch("subprocess.run", return_value=mock_proc):
            with pytest.raises(RuntimeError, match="JSON-RPC error"):
                adapter._jsonrpc("unknownMethod")

    def test_jsonrpc_multiline_output(self):
        """signal-cli may emit status lines before the JSON response."""
        adapter = self._make_adapter()
        output = "Connecting...\n" + json.dumps(
            {"jsonrpc": "2.0", "id": 1, "result": {"status": "ok"}}
        ) + "\n"
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = output
        mock_proc.stderr = ""

        with patch("subprocess.run", return_value=mock_proc):
            result = adapter._jsonrpc("testMethod")
            assert result["result"] == {"status": "ok"}

    def test_jsonrpc_no_params(self):
        """When called with no params, account is still injected."""
        adapter = self._make_adapter()
        rpc_response = json.dumps({"jsonrpc": "2.0", "id": 1, "result": []})
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = rpc_response + "\n"
        mock_proc.stderr = ""

        with patch("subprocess.run", return_value=mock_proc) as mock_run:
            adapter._jsonrpc("listAccounts")
            input_data = json.loads(mock_run.call_args[1]["input"].strip())
            assert input_data["params"] == {"account": "+15551234567"}


class TestSignalAdapterRegistration:
    def test_registered_in_registry(self):
        from merkaba.integrations.base import ADAPTER_REGISTRY

        assert "signal" in ADAPTER_REGISTRY
        assert ADAPTER_REGISTRY["signal"] is SignalAdapter

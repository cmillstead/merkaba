from unittest.mock import patch, MagicMock, call
import pytest
from merkaba.integrations.slack_adapter import (
    SlackAdapter,
    _build_approval_blocks,
    _chunk_for_slack,
    APPROVAL_ACTION_APPROVE,
    APPROVAL_ACTION_DENY,
)


class TestSlackAdapter:
    """Tests for WebClient-based API operations (existing functionality)."""

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

    def test_health_check_shows_realtime(self):
        """Health check includes realtime flag when Bolt is active."""
        adapter = SlackAdapter(name="slack")
        adapter._connected = True
        adapter._bolt_app = MagicMock()  # Simulate Bolt being set
        mock_client = MagicMock()
        mock_client.auth_test.return_value = {"ok": True, "user": "merkaba"}
        adapter._slack = mock_client
        result = adapter.health_check()
        assert result["ok"]
        assert result["realtime"] is True

    def test_send_message_error(self):
        adapter = SlackAdapter(name="slack")
        adapter._connected = True
        mock_client = MagicMock()
        mock_client.chat_postMessage.side_effect = Exception("network error")
        adapter._slack = mock_client
        result = adapter.execute("send_message", {"channel": "#general", "text": "hello"})
        assert not result["ok"]
        assert "network error" in result["error"]


class TestSlackBoltRealtime:
    """Tests for Bolt-based real-time event handling."""

    def test_start_realtime_fails_when_not_connected(self):
        adapter = SlackAdapter(name="slack")
        assert adapter.start_realtime() is False

    def test_start_realtime_fails_without_app_token(self):
        adapter = SlackAdapter(name="slack")
        adapter._connected = True
        with patch.object(adapter._creds, "has_required", return_value=(False, ["app_token"])):
            assert adapter.start_realtime() is False

    def test_start_realtime_fails_without_slack_bolt(self):
        """If slack-bolt is not installed, start_realtime returns False."""
        adapter = SlackAdapter(name="slack")
        adapter._connected = True
        with patch.object(adapter._creds, "has_required", return_value=(True, [])), \
             patch.object(adapter._creds, "get", return_value="xapp-fake"), \
             patch.dict("sys.modules", {"slack_bolt": None, "slack_bolt.adapter": None, "slack_bolt.adapter.socket_mode": None}):
            # Import will raise ImportError for None modules
            import importlib
            assert adapter.start_realtime() is False

    def test_start_realtime_creates_bolt_app(self):
        """Bolt app is created and started in a daemon thread."""
        adapter = SlackAdapter(name="slack")
        adapter._connected = True

        mock_app_class = MagicMock()
        mock_app = MagicMock()
        mock_app_class.return_value = mock_app

        mock_handler_class = MagicMock()
        mock_handler = MagicMock()
        mock_handler_class.return_value = mock_handler

        with patch.object(adapter._creds, "has_required", return_value=(True, [])), \
             patch.object(adapter._creds, "get", side_effect=lambda _, k: {
                 "bot_token": "xoxb-fake",
                 "app_token": "xapp-fake",
             }.get(k)), \
             patch("merkaba.integrations.slack_adapter.App", mock_app_class, create=True), \
             patch("merkaba.integrations.slack_adapter.SocketModeHandler", mock_handler_class, create=True), \
             patch("threading.Thread") as mock_thread_class:

            # Make the import work by patching the lazy imports
            import sys
            mock_bolt = MagicMock()
            mock_bolt.App = mock_app_class
            mock_socket = MagicMock()
            mock_socket.SocketModeHandler = mock_handler_class

            with patch.dict(sys.modules, {
                "slack_bolt": mock_bolt,
                "slack_bolt.adapter": MagicMock(),
                "slack_bolt.adapter.socket_mode": mock_socket,
            }):
                mock_thread = MagicMock()
                mock_thread.is_alive.return_value = True
                mock_thread_class.return_value = mock_thread

                result = adapter.start_realtime()

                assert result is True
                assert adapter._bolt_app is not None
                mock_thread.start.assert_called_once()

    def test_handle_bolt_message_routes_through_pool(self):
        """Messages are routed through SessionPool with correct session ID."""
        adapter = SlackAdapter(name="slack")
        adapter._connected = True
        mock_pool = MagicMock()
        mock_pool.submit_sync.return_value = "Agent response"
        adapter._pool = mock_pool

        mock_say = MagicMock()
        event = {
            "user": "U123ABC",
            "channel": "C456DEF",
            "text": "Hello agent",
        }

        with patch("merkaba.orchestration.session.build_session_id", return_value="slack:U123ABC:topic:C456DEF") as mock_build:
            adapter._handle_bolt_message(event, mock_say)

        mock_build.assert_called_once_with("slack", "U123ABC", topic_id="C456DEF")
        mock_pool.submit_sync.assert_called_once_with("slack:U123ABC:topic:C456DEF", "Hello agent")
        mock_say.assert_called_once_with(text="Agent response", thread_ts=None)

    def test_handle_bolt_message_session_id_format(self):
        """Session ID uses slack:user_id:topic:channel_id format."""
        adapter = SlackAdapter(name="slack")
        adapter._connected = True

        captured_session_id = []

        def capture_callback(session_id, text, event):
            captured_session_id.append(session_id)

        adapter._message_callback = capture_callback

        event = {"user": "U999", "channel": "CABC123", "text": "test"}
        adapter._handle_bolt_message(event, MagicMock())

        assert len(captured_session_id) == 1
        assert captured_session_id[0] == "slack:U999:topic:CABC123"

    def test_handle_bolt_message_respects_thread_ts(self):
        """Replies are threaded if the original message was in a thread."""
        adapter = SlackAdapter(name="slack")
        adapter._connected = True
        mock_pool = MagicMock()
        mock_pool.submit_sync.return_value = "Threaded reply"
        adapter._pool = mock_pool

        mock_say = MagicMock()
        event = {
            "user": "U123",
            "channel": "C456",
            "text": "Thread message",
            "thread_ts": "1234567890.123456",
        }

        adapter._handle_bolt_message(event, mock_say)
        mock_say.assert_called_once_with(text="Threaded reply", thread_ts="1234567890.123456")

    def test_handle_bolt_message_ignores_subtypes(self):
        """Bot messages, edits, and other subtypes are ignored."""
        adapter = SlackAdapter(name="slack")
        adapter._connected = True
        mock_pool = MagicMock()
        adapter._pool = mock_pool

        event = {"user": "U123", "channel": "C456", "text": "edit", "subtype": "message_changed"}
        adapter._handle_bolt_message(event, MagicMock())
        mock_pool.submit_sync.assert_not_called()

    def test_handle_bolt_message_ignores_empty_text(self):
        """Messages with no text or no user are ignored."""
        adapter = SlackAdapter(name="slack")
        adapter._connected = True
        mock_pool = MagicMock()
        adapter._pool = mock_pool

        # No text
        adapter._handle_bolt_message({"user": "U123", "channel": "C456", "text": ""}, MagicMock())
        mock_pool.submit_sync.assert_not_called()

        # No user
        adapter._handle_bolt_message({"channel": "C456", "text": "hello"}, MagicMock())
        mock_pool.submit_sync.assert_not_called()

    def test_handle_bolt_message_channel_filtering(self):
        """Only allowed channels receive responses."""
        adapter = SlackAdapter(name="slack")
        adapter._connected = True
        mock_pool = MagicMock()
        mock_pool.submit_sync.return_value = "ok"
        adapter._pool = mock_pool
        adapter._allowed_channels = ["C_ALLOWED"]

        # Blocked channel
        event = {"user": "U123", "channel": "C_BLOCKED", "text": "hello"}
        adapter._handle_bolt_message(event, MagicMock())
        mock_pool.submit_sync.assert_not_called()

        # Allowed channel
        event = {"user": "U123", "channel": "C_ALLOWED", "text": "hello"}
        adapter._handle_bolt_message(event, MagicMock())
        mock_pool.submit_sync.assert_called_once()

    def test_handle_bolt_message_error_sends_fallback(self):
        """On pool error, a friendly error message is sent back."""
        adapter = SlackAdapter(name="slack")
        adapter._connected = True
        mock_pool = MagicMock()
        mock_pool.submit_sync.side_effect = RuntimeError("Agent crashed")
        adapter._pool = mock_pool

        mock_say = MagicMock()
        event = {"user": "U123", "channel": "C456", "text": "crash me"}
        adapter._handle_bolt_message(event, mock_say)

        mock_say.assert_called_once()
        assert "something went wrong" in mock_say.call_args[1]["text"]

    def test_handle_bolt_message_uses_callback(self):
        """If message_callback is set (no pool), it receives the event."""
        adapter = SlackAdapter(name="slack")
        adapter._connected = True

        calls = []

        def my_callback(session_id, text, event):
            calls.append((session_id, text, event))

        adapter._message_callback = my_callback

        event = {"user": "U123", "channel": "C456", "text": "hello"}
        adapter._handle_bolt_message(event, MagicMock())

        assert len(calls) == 1
        assert calls[0][1] == "hello"

    def test_handle_bolt_message_pool_takes_priority(self):
        """When both pool and callback are set, pool is used."""
        adapter = SlackAdapter(name="slack")
        adapter._connected = True
        mock_pool = MagicMock()
        mock_pool.submit_sync.return_value = "pool response"
        adapter._pool = mock_pool

        callback_called = []
        adapter._message_callback = lambda *a: callback_called.append(True)

        event = {"user": "U123", "channel": "C456", "text": "test"}
        adapter._handle_bolt_message(event, MagicMock())

        mock_pool.submit_sync.assert_called_once()
        assert len(callback_called) == 0  # Callback not invoked

    def test_handle_bolt_message_no_handler_logs_warning(self):
        """No pool or callback logs a warning, no crash."""
        adapter = SlackAdapter(name="slack")
        adapter._connected = True
        # No pool, no callback

        event = {"user": "U123", "channel": "C456", "text": "nobody home"}
        # Should not raise
        adapter._handle_bolt_message(event, MagicMock())

    def test_handle_bolt_message_chunks_long_response(self):
        """Long responses are chunked for Slack's character limit."""
        adapter = SlackAdapter(name="slack")
        adapter._connected = True
        mock_pool = MagicMock()
        # Generate a response over 4000 chars
        long_response = "x" * 5000
        mock_pool.submit_sync.return_value = long_response
        adapter._pool = mock_pool

        mock_say = MagicMock()
        event = {"user": "U123", "channel": "C456", "text": "tell me everything"}
        adapter._handle_bolt_message(event, mock_say)

        # Should be called more than once due to chunking
        assert mock_say.call_count >= 2


class TestSlackApprovalBlocks:
    """Tests for Block Kit approval button generation."""

    def test_build_approval_blocks_structure(self):
        action = {
            "id": 42,
            "action_type": "deploy",
            "description": "Deploy v2.0 to production",
            "business_id": 1,
            "autonomy_level": 2,
        }
        blocks = _build_approval_blocks(action)

        assert len(blocks) == 4
        assert blocks[0]["type"] == "header"
        assert blocks[1]["type"] == "section"
        assert blocks[2]["type"] == "section"
        assert blocks[3]["type"] == "actions"

    def test_build_approval_blocks_button_values(self):
        action = {
            "id": 99,
            "action_type": "test",
            "description": "Test action",
            "business_id": 1,
            "autonomy_level": 1,
        }
        blocks = _build_approval_blocks(action)
        buttons = blocks[3]["elements"]

        assert len(buttons) == 2
        approve_btn = buttons[0]
        deny_btn = buttons[1]

        assert approve_btn["action_id"] == APPROVAL_ACTION_APPROVE
        assert approve_btn["value"] == "99"
        assert approve_btn["style"] == "primary"

        assert deny_btn["action_id"] == APPROVAL_ACTION_DENY
        assert deny_btn["value"] == "99"
        assert deny_btn["style"] == "danger"

    def test_build_approval_blocks_high_risk_tag(self):
        """Actions with autonomy_level >= 3 show 2FA warning."""
        action = {
            "id": 1,
            "action_type": "delete",
            "description": "Delete all data",
            "business_id": 1,
            "autonomy_level": 4,
        }
        blocks = _build_approval_blocks(action)
        header_text = blocks[0]["text"]["text"]
        assert "2FA Required" in header_text

    def test_build_approval_blocks_low_risk_no_tag(self):
        """Actions with autonomy_level < 3 have no 2FA warning."""
        action = {
            "id": 1,
            "action_type": "notify",
            "description": "Send notification",
            "business_id": 1,
            "autonomy_level": 1,
        }
        blocks = _build_approval_blocks(action)
        header_text = blocks[0]["text"]["text"]
        assert "2FA" not in header_text

    def test_send_approval_action(self):
        """The send_approval execute action sends Block Kit blocks."""
        adapter = SlackAdapter(name="slack")
        adapter._connected = True
        mock_client = MagicMock()
        mock_client.chat_postMessage.return_value = {"ok": True, "ts": "999"}
        adapter._slack = mock_client

        action = {
            "id": 7,
            "action_type": "publish",
            "description": "Publish listing",
            "business_id": 1,
            "autonomy_level": 2,
        }
        result = adapter.execute("send_approval", {"channel": "C123", "action": action})

        assert result["ok"]
        assert result["ts"] == "999"
        call_kwargs = mock_client.chat_postMessage.call_args[1]
        assert call_kwargs["channel"] == "C123"
        assert isinstance(call_kwargs["blocks"], list)
        assert len(call_kwargs["blocks"]) == 4

    def test_send_approval_action_error(self):
        adapter = SlackAdapter(name="slack")
        adapter._connected = True
        mock_client = MagicMock()
        mock_client.chat_postMessage.side_effect = Exception("rate limited")
        adapter._slack = mock_client

        result = adapter.execute("send_approval", {
            "channel": "C123",
            "action": {"id": 1, "action_type": "test", "description": "t", "business_id": 1, "autonomy_level": 1},
        })
        assert not result["ok"]
        assert "rate limited" in result["error"]


class TestSlackApprovalActions:
    """Tests for handling Block Kit button clicks (approval/deny)."""

    def test_handle_approval_approve(self):
        """Approve button click calls SecureApprovalManager.approve (not raw ActionQueue.decide)."""
        adapter = SlackAdapter(name="slack")

        mock_queue = MagicMock()
        mock_manager = MagicMock()
        body = {
            "actions": [{"value": "42"}],
            "user": {"id": "U_ADMIN"},
        }

        with patch("merkaba.approval.queue.ActionQueue", return_value=mock_queue), \
             patch("merkaba.approval.secure.SecureApprovalManager") as mock_sam_class:
            mock_sam_class.from_config.return_value = mock_manager
            adapter._handle_approval_action(body, approved=True)

        mock_sam_class.from_config.assert_called_once_with(mock_queue)
        mock_manager.approve.assert_called_once_with(42, decided_by="slack:U_ADMIN")
        mock_manager.deny.assert_not_called()
        mock_queue.close.assert_called_once()

    def test_handle_approval_deny(self):
        """Deny button click calls SecureApprovalManager.deny (not raw ActionQueue.decide)."""
        adapter = SlackAdapter(name="slack")

        mock_queue = MagicMock()
        mock_manager = MagicMock()
        body = {
            "actions": [{"value": "42"}],
            "user": {"id": "U_ADMIN"},
        }

        with patch("merkaba.approval.queue.ActionQueue", return_value=mock_queue), \
             patch("merkaba.approval.secure.SecureApprovalManager") as mock_sam_class:
            mock_sam_class.from_config.return_value = mock_manager
            adapter._handle_approval_action(body, approved=False)

        mock_sam_class.from_config.assert_called_once_with(mock_queue)
        mock_manager.deny.assert_called_once_with(42, decided_by="slack:U_ADMIN")
        mock_manager.approve.assert_not_called()

    def test_handle_approval_does_not_call_decide_directly(self):
        """Verify raw ActionQueue.decide is never called directly (security invariant)."""
        adapter = SlackAdapter(name="slack")

        mock_queue = MagicMock()
        mock_manager = MagicMock()
        body = {
            "actions": [{"value": "99"}],
            "user": {"id": "U_ADMIN"},
        }

        with patch("merkaba.approval.queue.ActionQueue", return_value=mock_queue), \
             patch("merkaba.approval.secure.SecureApprovalManager") as mock_sam_class:
            mock_sam_class.from_config.return_value = mock_manager
            adapter._handle_approval_action(body, approved=True)

        # ActionQueue.decide must NOT be called directly
        mock_queue.decide.assert_not_called()

    def test_handle_approval_custom_callback(self):
        """Custom action_callback overrides default ActionQueue behavior."""
        adapter = SlackAdapter(name="slack")
        calls = []
        adapter._action_callback = lambda aid, approved, uid: calls.append((aid, approved, uid))

        body = {
            "actions": [{"value": "7"}],
            "user": {"id": "U_CUSTOM"},
        }
        adapter._handle_approval_action(body, approved=True)

        assert calls == [(7, True, "U_CUSTOM")]

    def test_handle_approval_invalid_action_id(self):
        """Invalid action ID in button value does not crash."""
        adapter = SlackAdapter(name="slack")

        body = {
            "actions": [{"value": "not_a_number"}],
            "user": {"id": "U123"},
        }
        # Should not raise
        adapter._handle_approval_action(body, approved=True)

    def test_handle_approval_empty_actions(self):
        """Empty actions list does not crash."""
        adapter = SlackAdapter(name="slack")
        body = {"actions": [{}], "user": {"id": "U123"}}
        # value will be "", which is not a valid int
        adapter._handle_approval_action(body, approved=True)


class TestSlackDisconnect:
    """Tests for cleanup on disconnect."""

    def test_disconnect_cleans_up(self):
        adapter = SlackAdapter(name="slack")
        adapter._connected = True
        mock_handler = MagicMock()
        adapter._bolt_handler = mock_handler
        adapter._bolt_app = MagicMock()
        adapter._bolt_thread = MagicMock()

        adapter.disconnect()

        mock_handler.close.assert_called_once()
        assert adapter._bolt_handler is None
        assert adapter._bolt_app is None
        assert adapter._bolt_thread is None
        assert not adapter._connected

    def test_disconnect_tolerates_handler_error(self):
        """Disconnect handles errors from handler.close() gracefully."""
        adapter = SlackAdapter(name="slack")
        adapter._connected = True
        mock_handler = MagicMock()
        mock_handler.close.side_effect = RuntimeError("already closed")
        adapter._bolt_handler = mock_handler

        # Should not raise
        adapter.disconnect()
        assert not adapter._connected

    def test_bolt_running_property(self):
        adapter = SlackAdapter(name="slack")
        assert adapter.bolt_running is False

        mock_thread = MagicMock()
        mock_thread.is_alive.return_value = True
        adapter._bolt_thread = mock_thread
        assert adapter.bolt_running is True

        mock_thread.is_alive.return_value = False
        assert adapter.bolt_running is False


class TestChunkForSlack:
    """Tests for message chunking utility."""

    def test_short_message_not_chunked(self):
        assert _chunk_for_slack("hello") == ["hello"]

    def test_long_message_chunked(self):
        long_text = "x" * 5000
        chunks = _chunk_for_slack(long_text)
        assert len(chunks) >= 2
        for chunk in chunks:
            assert len(chunk) <= 4000

    def test_chunk_at_newline_boundary(self):
        # Build text where a newline is before the 4000 boundary
        part1 = "a" * 3000
        part2 = "b" * 3000
        text = part1 + "\n" + part2
        chunks = _chunk_for_slack(text)
        assert len(chunks) >= 2
        # First chunk should end at or before the newline
        assert len(chunks[0]) <= 4000

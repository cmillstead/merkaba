"""Slack integration adapter.

Provides both WebClient API operations (send_message, read_messages, etc.)
and Bolt-based real-time event handling for interactive messaging.

Bolt (slack-bolt) is an optional dependency. The adapter works without it
for API-only usage. Call start_realtime() to activate event-driven mode.
"""

import logging
import threading
from dataclasses import dataclass, field
from typing import Any

from merkaba.integrations.base import IntegrationAdapter, register_adapter
from merkaba.integrations.credentials import CredentialManager

logger = logging.getLogger(__name__)

REQUIRED_CREDENTIALS = ["bot_token"]
BOLT_CREDENTIALS = ["app_token"]  # Socket Mode requires app-level token

# Block Kit callback action IDs
APPROVAL_ACTION_APPROVE = "merkaba_approve"
APPROVAL_ACTION_DENY = "merkaba_deny"


def _build_approval_blocks(action: dict[str, Any]) -> list[dict]:
    """Build Slack Block Kit blocks for an approval request.

    Returns a list of block dicts suitable for chat_postMessage(blocks=...).
    Includes Approve/Deny buttons with the action ID encoded in the value.
    """
    action_id = action["id"]
    risk_tag = ""
    autonomy = action.get("autonomy_level", 1)
    if autonomy >= 3:
        risk_tag = " :warning: 2FA Required"

    return [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"Approval Required{risk_tag}",
            },
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Action:*\n{action['action_type']}"},
                {"type": "mrkdwn", "text": f"*ID:*\n#{action_id}"},
                {"type": "mrkdwn", "text": f"*Business:*\n{action.get('business_id', 'N/A')}"},
                {"type": "mrkdwn", "text": f"*Level:*\n{autonomy}"},
            ],
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Description:*\n{action.get('description', 'No description')}",
            },
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Approve"},
                    "style": "primary",
                    "action_id": APPROVAL_ACTION_APPROVE,
                    "value": str(action_id),
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Deny"},
                    "style": "danger",
                    "action_id": APPROVAL_ACTION_DENY,
                    "value": str(action_id),
                },
            ],
        },
    ]


@dataclass
class SlackAdapter(IntegrationAdapter):
    """Slack integration with WebClient API and optional Bolt real-time events.

    API mode (connect): Uses slack_sdk.WebClient for send/read/list/react.
    Real-time mode (start_realtime): Uses slack_bolt in Socket Mode for
    event-driven message handling routed through SessionPool.
    """

    _creds: CredentialManager = field(default_factory=CredentialManager, init=False, repr=False)
    _slack: object = field(default=None, init=False, repr=False)
    _bolt_app: object = field(default=None, init=False, repr=False)
    _bolt_handler: object = field(default=None, init=False, repr=False)
    _bolt_thread: threading.Thread | None = field(default=None, init=False, repr=False)
    _pool: object = field(default=None, init=False, repr=False)
    _message_callback: Any = field(default=None, init=False, repr=False)
    _action_callback: Any = field(default=None, init=False, repr=False)
    _allowed_channels: list[str] | None = field(default=None, init=False, repr=False)

    def connect(self) -> bool:
        ok, missing = self._creds.has_required("slack", REQUIRED_CREDENTIALS)
        if not ok:
            logger.warning("Slack adapter missing credentials: %s", missing)
            self._connected = False
            return False
        from slack_sdk import WebClient
        token = self._creds.get("slack", "bot_token")
        self._slack = WebClient(token=token)
        self._connected = True
        return True

    def execute(self, action: str, params: dict | None = None) -> dict:
        params = params or {}
        actions = {
            "send_message": self._send_message,
            "read_messages": self._read_messages,
            "list_channels": self._list_channels,
            "react": self._react,
            "send_approval": self._send_approval,
        }
        handler = actions.get(action)
        if not handler:
            return {"ok": False, "error": f"Unknown action: {action}"}
        return handler(params)

    def health_check(self) -> dict:
        if not self._connected or not self._slack:
            return {"ok": False, "adapter": "slack", "error": "Not connected"}
        try:
            resp = self._slack.auth_test()
            info = {"ok": True, "adapter": "slack", "user": resp.get("user")}
            if self._bolt_app is not None:
                info["realtime"] = True
            return info
        except Exception as e:
            return {"ok": False, "adapter": "slack", "error": str(e)}

    def disconnect(self) -> None:
        """Stop Bolt handler and clean up."""
        if self._bolt_handler is not None:
            try:
                self._bolt_handler.close()
            except Exception as e:
                logger.debug("Failed to close Slack Bolt handler: %s", e, exc_info=True)
            self._bolt_handler = None
        self._bolt_app = None
        self._bolt_thread = None
        self._connected = False
        logger.info("Slack adapter disconnected")

    # --- Real-time (Bolt) ---

    def start_realtime(
        self,
        pool: Any | None = None,
        message_callback: Any | None = None,
        action_callback: Any | None = None,
        allowed_channels: list[str] | None = None,
    ) -> bool:
        """Start Bolt Socket Mode for real-time event handling.

        Args:
            pool: A SessionPool instance. If provided, messages are routed
                through pool.submit() for per-session Agent handling.
            message_callback: Optional callback(session_id, text, event) for
                custom message handling. If both pool and callback are given,
                pool takes priority.
            action_callback: Optional callback(action_id, approved, user_id)
                for custom approval button handling.
            allowed_channels: If set, only respond to messages from these
                channel IDs. None means respond everywhere.

        Returns:
            True if Bolt was started, False on error.
        """
        if not self._connected:
            logger.error("Cannot start realtime: adapter not connected")
            return False

        # Check for app-level token (required for Socket Mode)
        ok, missing = self._creds.has_required("slack", BOLT_CREDENTIALS)
        if not ok:
            logger.warning("Slack Bolt requires credentials: %s", missing)
            return False

        try:
            from slack_bolt import App
            from slack_bolt.adapter.socket_mode import SocketModeHandler
        except ImportError:
            logger.error(
                "slack-bolt is not installed. Install with: pip install slack-bolt"
            )
            return False

        self._pool = pool
        self._message_callback = message_callback
        self._action_callback = action_callback
        self._allowed_channels = allowed_channels

        bot_token = self._creds.get("slack", "bot_token")
        app_token = self._creds.get("slack", "app_token")

        self._bolt_app = App(token=bot_token)
        self._register_bolt_handlers()

        self._bolt_handler = SocketModeHandler(self._bolt_app, app_token)

        # Run in a daemon thread so it doesn't block the caller
        self._bolt_thread = threading.Thread(
            target=self._bolt_handler.start,
            daemon=True,
            name="slack-bolt",
        )
        self._bolt_thread.start()
        logger.info("Slack Bolt real-time started (Socket Mode)")
        return True

    def _register_bolt_handlers(self) -> None:
        """Register message and action handlers on the Bolt app."""
        app = self._bolt_app

        @app.event("message")
        def handle_message(event, say):
            self._handle_bolt_message(event, say)

        @app.action(APPROVAL_ACTION_APPROVE)
        def handle_approve(ack, body):
            ack()
            self._handle_approval_action(body, approved=True)

        @app.action(APPROVAL_ACTION_DENY)
        def handle_deny(ack, body):
            ack()
            self._handle_approval_action(body, approved=False)

    def _handle_bolt_message(self, event: dict, say) -> None:
        """Handle an incoming Slack message event.

        Builds a session ID in the format slack:user_id:topic:channel_id
        and routes through SessionPool or message_callback.
        """
        # Ignore bot messages, message_changed, etc.
        if event.get("subtype"):
            return

        user_id = event.get("user", "")
        channel_id = event.get("channel", "")
        text = event.get("text", "")
        thread_ts = event.get("thread_ts")

        if not user_id or not text:
            return

        # Channel filtering
        if self._allowed_channels is not None and channel_id not in self._allowed_channels:
            return

        # Build session ID: slack:user_id:topic:channel_id
        from merkaba.orchestration.session import build_session_id
        session_id = build_session_id("slack", user_id, topic_id=channel_id)

        logger.info("Slack message from %s in %s (length=%d)", user_id, channel_id, len(text))
        logger.debug("Slack message content: %s", text[:80])

        # Route through pool or callback
        if self._pool is not None:
            try:
                response = self._pool.submit_sync(session_id, text)
                # Chunk long messages for Slack's 4000-char limit
                chunks = _chunk_for_slack(response)
                for chunk in chunks:
                    say(text=chunk, thread_ts=thread_ts)
            except Exception as e:
                logger.error("Error processing Slack message: %s", e)
                say(text="Sorry, something went wrong processing your message.", thread_ts=thread_ts)
        elif self._message_callback is not None:
            try:
                self._message_callback(session_id, text, event)
            except Exception as e:
                logger.error("Error in Slack message callback: %s", e)
        else:
            logger.warning("Slack message received but no pool or callback configured")

    def _handle_approval_action(self, body: dict, approved: bool) -> None:
        """Handle an approval button click from Block Kit."""
        action_data = body.get("actions", [{}])[0]
        action_id_str = action_data.get("value", "")
        user_id = body.get("user", {}).get("id", "unknown")

        try:
            action_id = int(action_id_str)
        except (ValueError, TypeError):
            logger.error("Invalid action ID in approval button: %s", action_id_str)
            return

        decision = "approved" if approved else "denied"
        logger.info("Slack approval: action #%d %s by %s", action_id, decision, user_id)

        if self._action_callback is not None:
            try:
                self._action_callback(action_id, approved, user_id)
            except Exception as e:
                logger.error("Error in approval callback: %s", e)
            return

        # Default: route through SecureApprovalManager for rate limiting and 2FA
        try:
            from merkaba.approval.queue import ActionQueue
            from merkaba.approval.secure import SecureApprovalManager
            queue = ActionQueue()
            try:
                manager = SecureApprovalManager.from_config(queue)
                if approved:
                    manager.approve(action_id, decided_by=f"slack:{user_id}")
                else:
                    manager.deny(action_id, decided_by=f"slack:{user_id}")
            finally:
                queue.close()
        except Exception as e:
            logger.error("Error processing approval: %s", e)

    @property
    def bolt_running(self) -> bool:
        """Check if Bolt is currently running."""
        return (
            self._bolt_thread is not None
            and self._bolt_thread.is_alive()
        )

    # --- API operations ---

    def _send_message(self, params: dict) -> dict:
        try:
            resp = self._slack.chat_postMessage(channel=params["channel"], text=params["text"])
            return {"ok": True, "ts": resp.get("ts")}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _read_messages(self, params: dict) -> dict:
        try:
            resp = self._slack.conversations_history(
                channel=params["channel"], limit=params.get("limit", 10)
            )
            return {"ok": True, "messages": resp.get("messages", [])}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _list_channels(self, params: dict) -> dict:
        try:
            resp = self._slack.conversations_list()
            return {"ok": True, "channels": resp.get("channels", [])}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _react(self, params: dict) -> dict:
        try:
            self._slack.reactions_add(
                channel=params["channel"], timestamp=params["timestamp"], name=params["emoji"]
            )
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _send_approval(self, params: dict) -> dict:
        """Send a Block Kit approval request to a channel.

        Params:
            channel: Channel ID to send the approval to.
            action: Action dict with id, action_type, description, etc.
        """
        try:
            action = params["action"]
            blocks = _build_approval_blocks(action)
            fallback_text = (
                f"Approval Required: {action['action_type']} - "
                f"{action.get('description', '')[:80]}"
            )
            resp = self._slack.chat_postMessage(
                channel=params["channel"],
                text=fallback_text,
                blocks=blocks,
            )
            return {"ok": True, "ts": resp.get("ts")}
        except Exception as e:
            return {"ok": False, "error": str(e)}


def _chunk_for_slack(text: str) -> list[str]:
    """Split a response into chunks that fit Slack's limit.

    Uses the delivery module if available, otherwise simple split.
    """
    try:
        from merkaba.integrations.delivery import chunk_message, CHANNEL_LIMITS
        return chunk_message(text, max_chars=CHANNEL_LIMITS.get("slack", 4000))
    except ImportError:
        # Fallback: simple chunking
        max_chars = 4000
        if len(text) <= max_chars:
            return [text]
        chunks = []
        while text:
            if len(text) <= max_chars:
                chunks.append(text)
                break
            # Try to split at newline
            idx = text.rfind("\n", 0, max_chars)
            if idx == -1:
                idx = text.rfind(" ", 0, max_chars)
            if idx == -1:
                idx = max_chars
            chunks.append(text[:idx])
            text = text[idx:].lstrip()
        return chunks


register_adapter("slack", SlackAdapter)

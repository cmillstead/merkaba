"""Slack integration adapter."""

import logging
from dataclasses import dataclass, field

from friday.integrations.base import IntegrationAdapter, register_adapter
from friday.integrations.credentials import CredentialManager

logger = logging.getLogger(__name__)

REQUIRED_CREDENTIALS = ["bot_token"]


@dataclass
class SlackAdapter(IntegrationAdapter):
    _creds: CredentialManager = field(default_factory=CredentialManager, init=False, repr=False)
    _slack: object = field(default=None, init=False, repr=False)

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
            return {"ok": True, "adapter": "slack", "user": resp.get("user")}
        except Exception as e:
            return {"ok": False, "adapter": "slack", "error": str(e)}

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


register_adapter("slack", SlackAdapter)

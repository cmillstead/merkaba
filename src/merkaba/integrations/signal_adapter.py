"""Signal integration adapter via signal-cli JSON-RPC."""

import json
import logging
import shutil
import subprocess
from dataclasses import dataclass, field

from merkaba.integrations.base import IntegrationAdapter, register_adapter
from merkaba.integrations.credentials import CredentialManager

logger = logging.getLogger(__name__)

REQUIRED_CREDENTIALS = ["account"]

# Default signal-cli path; overridden if credential "signal_cli_path" is set
DEFAULT_SIGNAL_CLI = "signal-cli"


def _build_session_id(recipient: str) -> str:
    """Build a session ID for Signal messages.

    Format: signal:phone_number or signal:group_id
    """
    from merkaba.orchestration.session import build_session_id

    return build_session_id("signal", recipient)


@dataclass
class SignalAdapter(IntegrationAdapter):
    """Signal channel adapter using signal-cli JSON-RPC subprocess."""

    _creds: CredentialManager = field(default_factory=CredentialManager, init=False, repr=False)
    _account: str | None = field(default=None, init=False, repr=False)
    _signal_cli: str = field(default=DEFAULT_SIGNAL_CLI, init=False, repr=False)
    _pool: object = field(default=None, init=False, repr=False)

    def connect(self) -> bool:
        """Connect by verifying signal-cli is available and account is configured."""
        ok, missing = self._creds.has_required("signal", REQUIRED_CREDENTIALS)
        if not ok:
            logger.warning("Signal adapter missing credentials: %s", missing)
            self._connected = False
            return False

        self._account = self._creds.get("signal", "account")

        # Allow custom signal-cli path
        cli_path = self._creds.get("signal", "signal_cli_path")
        if cli_path:
            self._signal_cli = cli_path

        # Verify signal-cli binary is reachable
        if not shutil.which(self._signal_cli):
            logger.warning("signal-cli binary not found: %s", self._signal_cli)
            self._connected = False
            return False

        self._connected = True
        return True

    def execute(self, action: str, params: dict | None = None) -> dict:
        params = params or {}
        actions = {
            "send_message": self._send_message,
            "read_messages": self._read_messages,
            "list_groups": self._list_groups,
            "get_contacts": self._get_contacts,
        }
        handler = actions.get(action)
        if not handler:
            return {"ok": False, "error": f"Unknown action: {action}"}
        return handler(params)

    def health_check(self) -> dict:
        if not self._connected or not self._account:
            return {"ok": False, "adapter": "signal", "error": "Not connected"}
        try:
            result = self._jsonrpc("listAccounts")
            accounts = result.get("result", [])
            registered = any(
                a.get("number") == self._account for a in accounts
            )
            return {
                "ok": registered,
                "adapter": "signal",
                "account": self._account,
                "registered": registered,
            }
        except Exception as e:
            return {"ok": False, "adapter": "signal", "error": str(e)}

    def disconnect(self) -> None:
        self._connected = False
        self._account = None

    # ── Action handlers ──────────────────────────────────────────────

    def _send_message(self, params: dict) -> dict:
        """Send a Signal message.

        Required params:
            recipient: phone number (+1234567890) or group ID
            text: message body
        Optional:
            group: bool - if True, send to group
        """
        recipient = params.get("recipient")
        text = params.get("text")
        if not recipient or not text:
            return {"ok": False, "error": "recipient and text are required"}

        is_group = params.get("group", False)

        try:
            rpc_params = {"message": text}
            if is_group:
                rpc_params["groupId"] = recipient
            else:
                rpc_params["recipient"] = [recipient]

            result = self._jsonrpc("send", rpc_params)

            session_id = _build_session_id(recipient)
            return {
                "ok": True,
                "session_id": session_id,
                "timestamp": result.get("result", {}).get("timestamp"),
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _read_messages(self, params: dict) -> dict:
        """Receive queued Signal messages.

        Optional params:
            timeout: seconds to wait for messages (default 1)
        """
        timeout = params.get("timeout", 1)
        try:
            result = self._jsonrpc("receive", {"timeout": timeout})
            raw_messages = result.get("result", [])

            messages = []
            for msg in raw_messages:
                envelope = msg if isinstance(msg, dict) else {}
                data_msg = envelope.get("dataMessage") or envelope.get("envelope", {}).get(
                    "dataMessage", {}
                )
                source = envelope.get("source") or envelope.get("envelope", {}).get("source", "")
                group_info = data_msg.get("groupInfo", {})
                group_id = group_info.get("groupId")
                sender_id = group_id if group_id else source

                messages.append(
                    {
                        "source": source,
                        "text": data_msg.get("message", ""),
                        "timestamp": data_msg.get("timestamp"),
                        "group_id": group_id,
                        "session_id": _build_session_id(sender_id) if sender_id else None,
                    }
                )
            return {"ok": True, "messages": messages}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _list_groups(self, params: dict) -> dict:
        """List Signal groups the account belongs to."""
        try:
            result = self._jsonrpc("listGroups")
            groups = result.get("result", [])
            return {
                "ok": True,
                "groups": [
                    {
                        "id": g.get("id"),
                        "name": g.get("name"),
                        "members": g.get("members", []),
                    }
                    for g in groups
                ],
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _get_contacts(self, params: dict) -> dict:
        """List Signal contacts."""
        try:
            result = self._jsonrpc("listContacts")
            contacts = result.get("result", [])
            return {
                "ok": True,
                "contacts": [
                    {
                        "number": c.get("number"),
                        "name": c.get("name"),
                        "profile_name": c.get("profileName"),
                    }
                    for c in contacts
                ],
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ── JSON-RPC transport ───────────────────────────────────────────

    def _jsonrpc(self, method: str, params: dict | None = None) -> dict:
        """Call signal-cli via JSON-RPC over subprocess stdin/stdout.

        signal-cli jsonRpc mode reads JSON-RPC requests from stdin line-by-line
        and writes responses to stdout.
        """
        request = {
            "jsonrpc": "2.0",
            "method": method,
            "id": 1,
        }
        if params:
            request["params"] = {**params, "account": self._account}
        else:
            request["params"] = {"account": self._account}

        input_data = json.dumps(request) + "\n"

        proc = subprocess.run(
            [self._signal_cli, "--output=json", "jsonRpc"],
            input=input_data,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if proc.returncode != 0:
            raise RuntimeError(f"signal-cli error: {proc.stderr.strip()}")

        # Parse the last non-empty line (signal-cli may emit status lines)
        lines = [line.strip() for line in proc.stdout.strip().splitlines() if line.strip()]
        if not lines:
            raise RuntimeError("signal-cli returned no output")

        response = json.loads(lines[-1])

        if "error" in response:
            raise RuntimeError(f"JSON-RPC error: {response['error']}")

        return response


register_adapter("signal", SignalAdapter)

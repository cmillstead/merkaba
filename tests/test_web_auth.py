# tests/test_web_auth.py
"""Tests for WebSocket query-param authentication and CORS origin configuration."""

import json
import os
import sys
import tempfile
from unittest.mock import MagicMock, patch

import pytest

# Stub heavy optional deps before importing merkaba modules
if "ollama" not in sys.modules:
    sys.modules["ollama"] = MagicMock()

HAS_DEPS = True
try:
    from fastapi.testclient import TestClient
    from starlette.websockets import WebSocketDisconnect
    from merkaba.web.app import create_app
    from merkaba.memory.store import MemoryStore
    from merkaba.orchestration.queue import TaskQueue
    from merkaba.approval.queue import ActionQueue
except ImportError:
    HAS_DEPS = False

pytestmark = pytest.mark.skipif(not HAS_DEPS, reason="Missing web dependencies")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_app(tmp_path, store_factory):
    """Create a test app with isolated temp databases."""
    overrides = {
        "memory_store": store_factory(MemoryStore, str(tmp_path / "memory.db")),
        "task_queue": store_factory(TaskQueue, str(tmp_path / "tasks.db")),
        "action_queue": store_factory(ActionQueue, str(tmp_path / "actions.db")),
        "merkaba_base_dir": str(tmp_path / "merkaba_home"),
    }
    os.makedirs(overrides["merkaba_base_dir"], exist_ok=True)
    return create_app(db_overrides=overrides)


# ---------------------------------------------------------------------------
# WebSocket query-param auth
# ---------------------------------------------------------------------------

class TestWebSocketQueryParamAuth:
    """Verify that ?token= is accepted for WebSocket connections when an API key
    is configured, and that missing / wrong tokens are rejected."""

    @pytest.fixture
    def auth_client(self, tmp_path, make_store):
        """App client with api_key configured and a real mock agent."""
        app = _make_app(tmp_path, make_store)
        with TestClient(app, raise_server_exceptions=False) as client:
            # Set an API key *after* the lifespan has run so the test controls it
            app.state.api_key = "test-secret-key"
            yield client, app

    def test_websocket_auth_query_param(self, auth_client):
        """WebSocket connect with ?token=<api_key> should be accepted."""
        client, app = auth_client

        mock_agent = MagicMock()
        mock_agent.run.return_value = "pong"
        mock_agent.permission_manager = MagicMock()

        with patch("merkaba.agent.Agent", return_value=mock_agent):
            with client.websocket_connect("/ws/chat?token=test-secret-key") as ws:
                ws.send_json({"message": "ping"})
                # Drain the thinking message
                msg1 = ws.receive_json()
                assert msg1["type"] == "thinking"
                # Receive the actual response — confirms the connection was accepted
                msg2 = ws.receive_json()
                assert msg2["type"] == "response"
                assert msg2["content"] == "pong"

    def test_websocket_auth_no_token_rejected(self, auth_client):
        """WebSocket connect without any token should be rejected with code 4001."""
        client, app = auth_client

        # TestClient raises WebSocketDisconnect when the server closes with an
        # error code.  We catch it and verify the close code.
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect("/ws/chat") as ws:
                # Server should reject immediately during the dependency check
                ws.receive_json()

        assert exc_info.value.code == 4001

    def test_websocket_auth_wrong_token_rejected(self, auth_client):
        """WebSocket connect with a wrong ?token= value should be rejected."""
        client, app = auth_client

        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect("/ws/chat?token=wrong-key") as ws:
                ws.receive_json()

        assert exc_info.value.code == 4001

    def test_websocket_auth_header_still_works(self, auth_client):
        """X-API-Key header authentication should continue to work alongside
        the new query-param support."""
        client, app = auth_client

        mock_agent = MagicMock()
        mock_agent.run.return_value = "header-ok"
        mock_agent.permission_manager = MagicMock()

        with patch("merkaba.agent.Agent", return_value=mock_agent):
            with client.websocket_connect(
                "/ws/chat",
                headers={"X-API-Key": "test-secret-key"},
            ) as ws:
                ws.send_json({"message": "hello"})
                msg1 = ws.receive_json()
                assert msg1["type"] == "thinking"
                msg2 = ws.receive_json()
                assert msg2["type"] == "response"
                assert msg2["content"] == "header-ok"

    def test_websocket_no_auth_required_when_no_key_configured(self, tmp_path, make_store):
        """When no api_key is configured, WebSocket connects without any token
        should be accepted."""
        app = _make_app(tmp_path, make_store)
        # api_key is None by default in db_overrides path (see lifespan)

        mock_agent = MagicMock()
        mock_agent.run.return_value = "open"
        mock_agent.permission_manager = MagicMock()

        with TestClient(app, raise_server_exceptions=False) as client:
            with patch("merkaba.agent.Agent", return_value=mock_agent):
                with client.websocket_connect("/ws/chat") as ws:
                    ws.send_json({"message": "hi"})
                    msg1 = ws.receive_json()
                    assert msg1["type"] == "thinking"
                    msg2 = ws.receive_json()
                    assert msg2["type"] == "response"


# ---------------------------------------------------------------------------
# WebSocket error handling
# ---------------------------------------------------------------------------

class TestWebSocketErrorHandling:
    """Verify that agent errors and oversized messages produce error frames."""

    @pytest.fixture
    def open_client(self, tmp_path, make_store):
        """App client without an API key (open access)."""
        app = _make_app(tmp_path, make_store)
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client, app

    def test_websocket_error_message_type(self, open_client):
        """When agent.run() raises an exception the client should receive
        {"type": "error"} rather than a hard disconnect."""
        client, app = open_client

        mock_agent = MagicMock()
        mock_agent.run.side_effect = RuntimeError("agent exploded")
        mock_agent.permission_manager = MagicMock()

        with patch("merkaba.agent.Agent", return_value=mock_agent):
            with client.websocket_connect("/ws/chat") as ws:
                ws.send_json({"message": "trigger error"})

                # First message: thinking indicator
                msg1 = ws.receive_json()
                assert msg1["type"] == "thinking"

                # Second message: error frame — not a crash
                msg2 = ws.receive_json()
                assert msg2["type"] == "error"
                # C1: Error content must be generic, not leak exception details
                assert "internal error" in msg2["content"].lower()

    def test_websocket_message_size_limit(self, open_client):
        """Sending a message larger than MAX_WS_MESSAGE_SIZE (64 KB) should
        return {"type": "error"} without invoking the agent."""
        client, app = open_client

        mock_agent = MagicMock()
        mock_agent.run.return_value = "should not reach here"
        mock_agent.permission_manager = MagicMock()

        # Build a JSON payload whose string representation exceeds 64 KB
        oversized_message = "x" * (64 * 1024 + 1)
        payload = json.dumps({"message": oversized_message})

        with patch("merkaba.agent.Agent", return_value=mock_agent):
            with client.websocket_connect("/ws/chat") as ws:
                ws.send_text(payload)

                msg = ws.receive_json()
                assert msg["type"] == "error"
                assert "too large" in msg["content"].lower()

                # Agent should not have been called
                mock_agent.run.assert_not_called()


# ---------------------------------------------------------------------------
# CORS origin configuration
# ---------------------------------------------------------------------------

class TestCorsOrigins:
    """Verify that cors_origins in config.json are merged into the middleware."""

    def test_cors_default_origins_present(self, tmp_path, make_store):
        """Without a config.json the default dev origins should be active.

        We verify indirectly: an OPTIONS preflight to a default dev origin must
        receive Access-Control-Allow-Origin back from the CORS middleware.
        """
        # Patch load_config to return empty dict, simulating absent config.json.
        with patch("merkaba.config.loader.load_config", return_value={}):
            app = create_app(db_overrides={
                "memory_store": make_store(MemoryStore, str(tmp_path / "m.db")),
                "task_queue": make_store(TaskQueue, str(tmp_path / "t.db")),
                "action_queue": make_store(ActionQueue, str(tmp_path / "a.db")),
                "merkaba_base_dir": str(tmp_path),
            })

        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.options(
                "/api/system/status",
                headers={
                    "Origin": "http://localhost:5173",
                    "Access-Control-Request-Method": "GET",
                },
            )
        assert resp.headers.get("access-control-allow-origin") == "http://localhost:5173"

    def test_cors_user_configured_origins_merged(self, tmp_path, make_store):
        """User-configured cors_origins in config.json should be included."""
        mock_cfg = {"cors_origins": ["https://app.example.com", "https://staging.example.com"]}

        with patch("merkaba.config.loader.load_config", return_value=mock_cfg):
            app = create_app(db_overrides={
                "memory_store": make_store(MemoryStore, str(tmp_path / "m.db")),
                "task_queue": make_store(TaskQueue, str(tmp_path / "t.db")),
                "action_queue": make_store(ActionQueue, str(tmp_path / "a.db")),
                "merkaba_base_dir": str(tmp_path),
            })

        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.options(
                "/api/system/status",
                headers={
                    "Origin": "https://app.example.com",
                    "Access-Control-Request-Method": "GET",
                },
            )
        assert resp.headers.get("access-control-allow-origin") == "https://app.example.com"

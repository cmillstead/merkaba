# tests/e2e/test_e2e_control.py
"""E2E tests for the Mission Control /api/control endpoints."""

import os
import sqlite3
import sys
from unittest.mock import MagicMock

import pytest

# Stub out heavy deps before importing
if "ollama" not in sys.modules:
    sys.modules["ollama"] = MagicMock()

HAS_DEPS = True
try:
    from fastapi.testclient import TestClient
    from merkaba.web.app import create_app
    from merkaba.memory.store import MemoryStore
    from merkaba.orchestration.queue import TaskQueue
    from merkaba.approval.queue import ActionQueue
except ImportError:
    HAS_DEPS = False

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(not HAS_DEPS, reason="Missing web dependencies"),
]


def _make_store(cls, db_path):
    """Create a store with check_same_thread=False for test cross-thread access."""
    obj = object.__new__(cls)
    obj.db_path = db_path
    db_dir = os.path.dirname(db_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    obj._conn = sqlite3.connect(db_path, check_same_thread=False)
    obj._conn.row_factory = sqlite3.Row
    obj._conn.execute("PRAGMA foreign_keys = ON")
    obj._create_tables()
    return obj


@pytest.fixture
def app_client(tmp_path):
    overrides = {
        "memory_store": _make_store(MemoryStore, str(tmp_path / "memory.db")),
        "task_queue": _make_store(TaskQueue, str(tmp_path / "tasks.db")),
        "action_queue": _make_store(ActionQueue, str(tmp_path / "actions.db")),
        "merkaba_base_dir": str(tmp_path / "merkaba_home"),
    }
    os.makedirs(overrides["merkaba_base_dir"], exist_ok=True)
    app = create_app(db_overrides=overrides)
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, app


@pytest.mark.e2e
class TestControlState:
    def test_get_control_state(self, app_client):
        client, app = app_client
        resp = client.get("/api/control/state")
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "state_update"
        assert "system" in data
        assert "agents" in data
        assert "workers" in data
        assert "connections" in data
        # System should have expected keys
        sys = data["system"]
        assert "status" in sys
        assert "memory_facts" in sys
        assert "pending_approvals" in sys
        assert "active_tasks" in sys

    def test_control_state_has_workers(self, app_client):
        client, app = app_client
        resp = client.get("/api/control/state")
        data = resp.json()
        # Should have at least the built-in workers
        worker_ids = [w["id"] for w in data["workers"]]
        assert "health_check" in worker_ids
        assert "research" in worker_ids

    def test_control_state_has_agent_tools(self, app_client):
        client, app = app_client
        resp = client.get("/api/control/state")
        data = resp.json()
        agents = data["agents"]
        assert len(agents) >= 1
        merkaba = agents[0]
        assert merkaba["id"] == "merkaba-prime"
        assert merkaba["name"] == "Merkaba"
        tool_names = [t["name"] for t in merkaba["tools"]]
        # Should have some built-in tools
        assert len(tool_names) > 0

    def test_control_connections(self, app_client):
        client, app = app_client
        resp = client.get("/api/control/state")
        data = resp.json()
        connections = data["connections"]
        # Each worker should have a connection from merkaba-prime
        for worker in data["workers"]:
            assert any(
                c["from"] == "merkaba-prime" and c["to"] == worker["id"]
                for c in connections
            ), f"Missing connection for worker {worker['id']}"


@pytest.mark.e2e
class TestControlWebSocket:
    def test_ws_control_sends_initial_state(self, app_client):
        client, app = app_client
        with client.websocket_connect("/ws/control") as ws:
            msg = ws.receive_json()
            assert msg["type"] == "state_update"
            assert "system" in msg
            assert "agents" in msg

    def test_ws_control_sends_heartbeat(self, app_client):
        """After initial state, should receive heartbeat updates."""
        client, app = app_client
        with client.websocket_connect("/ws/control") as ws:
            msg1 = ws.receive_json()
            assert msg1["type"] == "state_update"
            # Second message should also be a state update (heartbeat)
            msg2 = ws.receive_json()
            assert msg2["type"] == "state_update"


@pytest.mark.e2e
class TestControlModel:
    def test_change_model(self, app_client):
        client, app = app_client
        resp = client.post("/api/control/model", json={
            "agent": "merkaba-prime",
            "model": "qwen3:8b",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["model"] == "qwen3:8b"

    def test_change_model_invalid_agent(self, app_client):
        client, app = app_client
        resp = client.post("/api/control/model", json={
            "agent": "nonexistent",
            "model": "qwen3:8b",
        })
        assert resp.status_code == 404


@pytest.mark.e2e
class TestControlIntegration:
    """Integration tests verifying model changes flow through state and WebSocket."""

    @pytest.fixture(autouse=True)
    def _reset_model_overrides(self):
        """Clear module-level model overrides so each test starts from defaults."""
        from merkaba.web.routes.control import _model_overrides
        _model_overrides.clear()
        yield
        _model_overrides.clear()

    def test_state_then_model_change_reflects_in_state(self, app_client):
        client, app = app_client
        # Get initial state — should use the default model
        resp = client.get("/api/control/state")
        initial_model = resp.json()["agents"][0]["model"]
        assert initial_model == "qwen3.5:122b"

        # Change model
        client.post("/api/control/model", json={
            "agent": "merkaba-prime",
            "model": "qwen3:8b",
        })

        # Verify state reflects the change
        resp = client.get("/api/control/state")
        assert resp.json()["agents"][0]["model"] == "qwen3:8b"

    def test_ws_reflects_model_change(self, app_client):
        client, app = app_client
        # Change model first
        client.post("/api/control/model", json={
            "agent": "merkaba-prime",
            "model": "qwen3:8b",
        })
        # WebSocket should show updated model
        with client.websocket_connect("/ws/control") as ws:
            msg = ws.receive_json()
            assert msg["agents"][0]["model"] == "qwen3:8b"


@pytest.mark.e2e
class TestWebSocketAuthGuard:
    """Verify WebSocket connections are rejected with close code 4001 when API key is invalid."""

    @pytest.fixture
    def authed_app_client(self, tmp_path):
        """App client with API key authentication enabled."""
        overrides = {
            "memory_store": _make_store(MemoryStore, str(tmp_path / "memory.db")),
            "task_queue": _make_store(TaskQueue, str(tmp_path / "tasks.db")),
            "action_queue": _make_store(ActionQueue, str(tmp_path / "actions.db")),
            "merkaba_base_dir": str(tmp_path / "merkaba_home"),
        }
        os.makedirs(overrides["merkaba_base_dir"], exist_ok=True)
        app = create_app(db_overrides=overrides)
        with TestClient(app, raise_server_exceptions=False) as client:
            # Set API key after lifespan has initialized (lifespan sets it to None)
            app.state.api_key = "test-secret-key"
            yield client, app

    def test_ws_rejected_without_api_key(self, authed_app_client):
        """WebSocket connection without API key should be closed with code 4001."""
        from starlette.websockets import WebSocketDisconnect

        client, app = authed_app_client
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect("/ws/control") as ws:
                ws.receive_json()
        assert exc_info.value.code == 4001

    def test_ws_rejected_with_wrong_api_key(self, authed_app_client):
        """WebSocket connection with wrong API key should be closed with code 4001."""
        from starlette.websockets import WebSocketDisconnect

        client, app = authed_app_client
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect(
                "/ws/control",
                headers={"X-API-Key": "wrong-key"},
            ) as ws:
                ws.receive_json()
        assert exc_info.value.code == 4001

    def test_ws_accepted_with_correct_api_key(self, authed_app_client):
        """WebSocket connection with correct API key should succeed."""
        client, app = authed_app_client
        with client.websocket_connect(
            "/ws/control",
            headers={"X-API-Key": "test-secret-key"},
        ) as ws:
            msg = ws.receive_json()
            assert msg["type"] == "state_update"

    def test_http_rejected_without_api_key(self, authed_app_client):
        """HTTP requests without API key should still get 401."""
        client, app = authed_app_client
        resp = client.get("/api/control/state")
        assert resp.status_code == 401

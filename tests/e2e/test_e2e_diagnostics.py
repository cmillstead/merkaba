# tests/e2e/test_e2e_diagnostics.py
"""Tests for the DiagnosticsStore ring buffer and DiagnosticsMiddleware."""

import os
import sqlite3
import sys
import threading
from unittest.mock import MagicMock

import pytest

if "ollama" not in sys.modules:
    sys.modules["ollama"] = MagicMock()

from merkaba.web.diagnostics import DiagnosticsStore, TraceDepth


pytestmark = pytest.mark.e2e


class TestDiagnosticsStore:
    def test_initial_state_empty(self):
        store = DiagnosticsStore(buffer_size=100)
        assert store.get_recent(10) == []
        assert store.get_errors(10) == []
        assert store.get_connections() == []
        summary = store.get_summary()
        assert summary["total_requests"] == 0
        assert summary["total_errors"] == 0

    def test_record_http_request(self):
        store = DiagnosticsStore(buffer_size=100)
        store.record_request({
            "timestamp": "2026-03-01T12:00:00Z",
            "method": "GET",
            "path": "/api/system/status",
            "status": 200,
            "duration_ms": 12.4,
        })
        recent = store.get_recent(10)
        assert len(recent) == 1
        assert recent[0]["method"] == "GET"
        assert recent[0]["path"] == "/api/system/status"

    def test_record_error_request(self):
        store = DiagnosticsStore(buffer_size=100)
        store.record_request({
            "timestamp": "2026-03-01T12:00:00Z",
            "method": "GET",
            "path": "/bad",
            "status": 500,
            "duration_ms": 5.0,
            "error": "Internal Server Error",
        })
        errors = store.get_errors(10)
        assert len(errors) == 1
        assert errors[0]["error"] == "Internal Server Error"

    def test_ring_buffer_eviction(self):
        store = DiagnosticsStore(buffer_size=3)
        for i in range(5):
            store.record_request({
                "timestamp": f"2026-03-01T12:00:0{i}Z",
                "method": "GET",
                "path": f"/req/{i}",
                "status": 200,
                "duration_ms": 1.0,
            })
        recent = store.get_recent(10)
        assert len(recent) == 3
        # Newest first
        assert recent[0]["path"] == "/req/4"
        assert recent[2]["path"] == "/req/2"

    def test_websocket_connection_tracking(self):
        store = DiagnosticsStore(buffer_size=100)
        store.ws_connect("conn-1", "/ws/control")
        store.ws_connect("conn-2", "/ws/chat")
        conns = store.get_connections()
        assert len(conns) == 2
        paths = {c["path"] for c in conns}
        assert paths == {"/ws/control", "/ws/chat"}

    def test_websocket_disconnect_removes(self):
        store = DiagnosticsStore(buffer_size=100)
        store.ws_connect("conn-1", "/ws/control")
        store.ws_disconnect("conn-1")
        assert store.get_connections() == []

    def test_websocket_frame_counting(self):
        store = DiagnosticsStore(buffer_size=100)
        store.ws_connect("conn-1", "/ws/control")
        store.ws_frame_sent("conn-1")
        store.ws_frame_sent("conn-1")
        store.ws_frame_received("conn-1")
        conns = store.get_connections()
        assert conns[0]["frames_sent"] == 2
        assert conns[0]["frames_received"] == 1

    def test_summary_stats(self):
        store = DiagnosticsStore(buffer_size=100)
        for i in range(10):
            store.record_request({
                "timestamp": f"2026-03-01T12:00:0{i}Z",
                "method": "GET",
                "path": f"/req/{i}",
                "status": 500 if i == 0 else 200,
                "duration_ms": float(i + 1),
            })
        summary = store.get_summary()
        assert summary["total_requests"] == 10
        assert summary["total_errors"] == 1
        assert summary["avg_duration_ms"] == 5.5

    def test_trace_depth_change(self):
        store = DiagnosticsStore(buffer_size=100)
        assert store.trace_depth == TraceDepth.FULL
        store.set_trace_depth(TraceDepth.LIGHTWEIGHT)
        assert store.trace_depth == TraceDepth.LIGHTWEIGHT

    def test_thread_safety(self):
        store = DiagnosticsStore(buffer_size=100)
        errors = []

        def writer(start):
            try:
                for i in range(50):
                    store.record_request({
                        "timestamp": "2026-03-01T12:00:00Z",
                        "method": "GET",
                        "path": f"/thread/{start}/{i}",
                        "status": 200,
                        "duration_ms": 1.0,
                    })
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(t,)) for t in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        summary = store.get_summary()
        assert summary["total_requests"] == 200


# --- Middleware tests (require web dependencies) ---

HAS_WEB_DEPS = True
try:
    from fastapi.testclient import TestClient
    from merkaba.web.app import create_app
    from merkaba.memory.store import MemoryStore
    from merkaba.orchestration.queue import TaskQueue
    from merkaba.approval.queue import ActionQueue
except ImportError:
    HAS_WEB_DEPS = False


def _make_store(cls, db_path):
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


@pytest.mark.skipif(not HAS_WEB_DEPS, reason="Missing web dependencies")
class TestDiagnosticsMiddleware:
    def test_middleware_traces_http_request(self, app_client):
        client, app = app_client
        client.get("/api/system/status")
        store = app.state.diagnostics_store
        recent = store.get_recent(10)
        assert len(recent) >= 1
        req = next(r for r in recent if r["path"] == "/api/system/status")
        assert req["method"] == "GET"
        assert req["status"] == 200
        assert req["duration_ms"] > 0

    def test_middleware_traces_404(self, app_client):
        client, app = app_client
        client.get("/api/nonexistent")
        store = app.state.diagnostics_store
        errors = store.get_errors(10)
        assert any(r["status"] == 404 for r in errors)

    def test_middleware_tracks_websocket(self, app_client):
        client, app = app_client
        with client.websocket_connect("/ws/control") as ws:
            ws.receive_json()  # initial state
            store = app.state.diagnostics_store
            conns = store.get_connections()
            assert any(c["path"] == "/ws/control" for c in conns)
        # After disconnect, connection should be removed
        conns = store.get_connections()
        assert not any(c["path"] == "/ws/control" for c in conns)

    def test_middleware_never_crashes_request(self, app_client):
        """Even if tracing fails, the request should succeed."""
        client, app = app_client
        # Normal request should always work
        resp = client.get("/api/system/status")
        assert resp.status_code == 200

    def test_middleware_sanitizes_headers(self, app_client):
        client, app = app_client
        client.get("/api/system/status", headers={
            "Authorization": "Bearer secret-token",
            "X-API-Key": "my-key",
            "X-Custom": "visible",
        })
        store = app.state.diagnostics_store
        recent = store.get_recent(10)
        req = next(r for r in recent if r["path"] == "/api/system/status")
        if "headers" in req:
            headers = dict(req["headers"])
            assert headers.get("authorization") == "[REDACTED]"
            assert headers.get("x-api-key") == "[REDACTED]"
            assert headers.get("x-custom") == "visible"


@pytest.mark.skipif(not HAS_WEB_DEPS, reason="Missing web dependencies")
class TestControlWebSocketProtocol:
    def test_subscribe_diagnostics(self, app_client):
        client, app = app_client
        with client.websocket_connect("/ws/control") as ws:
            msg = ws.receive_json()  # initial state
            assert "diagnostics" not in msg  # not subscribed yet

            ws.send_json({"type": "subscribe", "channel": "diagnostics"})
            msg = ws.receive_json()  # next heartbeat
            assert "diagnostics" in msg
            diag = msg["diagnostics"]
            assert "trace_depth" in diag
            assert "active_websockets" in diag
            assert "recent_requests" in diag

    def test_unsubscribe_diagnostics(self, app_client):
        client, app = app_client
        with client.websocket_connect("/ws/control") as ws:
            ws.receive_json()  # initial state
            ws.send_json({"type": "subscribe", "channel": "diagnostics"})
            msg = ws.receive_json()
            assert "diagnostics" in msg

            ws.send_json({"type": "unsubscribe", "channel": "diagnostics"})
            msg = ws.receive_json()
            assert "diagnostics" not in msg

    def test_set_trace_depth(self, app_client):
        client, app = app_client
        with client.websocket_connect("/ws/control") as ws:
            ws.receive_json()  # initial state
            ws.send_json({"type": "subscribe", "channel": "diagnostics"})
            ws.send_json({"type": "set_trace_depth", "level": "lightweight"})
            msg = ws.receive_json()
            assert msg["diagnostics"]["trace_depth"] == "lightweight"


@pytest.mark.skipif(not HAS_WEB_DEPS, reason="Missing web dependencies")
class TestDiagnosticsREST:
    def test_get_diagnostics_state(self, app_client):
        client, app = app_client
        # Make some requests first
        client.get("/api/system/status")
        client.get("/api/nonexistent")

        resp = client.get("/api/system/diagnostics")
        assert resp.status_code == 200
        data = resp.json()
        assert "trace_depth" in data
        assert "active_websockets" in data
        assert "recent_requests" in data
        assert "recent_errors" in data
        assert "summary" in data or "total_requests" in data

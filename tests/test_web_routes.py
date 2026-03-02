"""Tests for Mission Control web API routes."""
import json
import sqlite3
import tempfile
import os
import sys
from unittest.mock import patch, MagicMock

import pytest

# Stub out heavy optional deps before importing merkaba modules
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

pytestmark = pytest.mark.skipif(not HAS_DEPS, reason="Missing web dependencies")


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
def app_client():
    """Create a test client with temp databases."""
    with tempfile.TemporaryDirectory() as tmpdir:
        memory_db = os.path.join(tmpdir, "memory.db")
        tasks_db = os.path.join(tmpdir, "tasks.db")
        actions_db = os.path.join(tmpdir, "actions.db")
        merkaba_dir = os.path.join(tmpdir, "merkaba_home")
        os.makedirs(merkaba_dir, exist_ok=True)

        overrides = {
            "memory_store": _make_store(MemoryStore, memory_db),
            "task_queue": _make_store(TaskQueue, tasks_db),
            "action_queue": _make_store(ActionQueue, actions_db),
            "merkaba_base_dir": merkaba_dir,
        }

        app = create_app(db_overrides=overrides)

        with TestClient(app, raise_server_exceptions=False) as client:
            yield client, app


# --- System routes ---

class TestSystemRoutes:
    def test_status(self, app_client):
        client, app = app_client
        resp = client.get("/api/system/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "ollama" in data
        assert "databases" in data
        assert "counts" in data

    def test_models(self, app_client):
        client, app = app_client
        resp = client.get("/api/system/models")
        assert resp.status_code == 200
        data = resp.json()
        assert "models" in data


# --- Business routes ---

class TestBusinessRoutes:
    def test_list_empty(self, app_client):
        client, app = app_client
        resp = client.get("/api/businesses")
        assert resp.status_code == 200
        assert resp.json() == {"businesses": []}

    def test_list_with_data(self, app_client):
        client, app = app_client
        store = app.state.memory_store
        store.add_business("Test Shop", "ecommerce", autonomy_level=2)
        resp = client.get("/api/businesses")
        data = resp.json()
        assert len(data["businesses"]) == 1
        assert data["businesses"][0]["name"] == "Test Shop"

    def test_get_business(self, app_client):
        client, app = app_client
        store = app.state.memory_store
        biz_id = store.add_business("Test Shop", "ecommerce")
        store.add_fact(biz_id, "product", "material", "wood")
        resp = client.get(f"/api/businesses/{biz_id}")
        data = resp.json()
        assert data["business"]["name"] == "Test Shop"
        assert len(data["facts"]) == 1


# --- Memory routes ---

class TestMemoryRoutes:
    def test_search(self, app_client):
        client, app = app_client
        resp = client.get("/api/memory/search?q=test")
        assert resp.status_code == 200
        data = resp.json()
        assert data["query"] == "test"
        assert "results" in data

    def test_facts_empty(self, app_client):
        client, app = app_client
        resp = client.get("/api/memory/facts")
        assert resp.status_code == 200
        assert resp.json() == {"facts": []}

    def test_facts_with_filter(self, app_client):
        client, app = app_client
        store = app.state.memory_store
        biz_id = store.add_business("Shop", "ecommerce")
        store.add_fact(biz_id, "product", "color", "blue")
        store.add_fact(biz_id, "pricing", "base", "$10")

        resp = client.get(f"/api/memory/facts?business_id={biz_id}&category=product")
        data = resp.json()
        assert len(data["facts"]) == 1
        assert data["facts"][0]["key"] == "color"

    def test_decisions(self, app_client):
        client, app = app_client
        store = app.state.memory_store
        biz_id = store.add_business("Shop", "ecommerce")
        store.add_decision(biz_id, "pricing", "Raise price", "Market demand")
        resp = client.get(f"/api/memory/decisions?business_id={biz_id}")
        data = resp.json()
        assert len(data["decisions"]) == 1

    def test_learnings(self, app_client):
        client, app = app_client
        store = app.state.memory_store
        store.add_learning("pricing", "Higher prices work", confidence=80)
        resp = client.get("/api/memory/learnings")
        data = resp.json()
        assert len(data["learnings"]) == 1


# --- Task routes ---

class TestTaskRoutes:
    def test_list_empty(self, app_client):
        client, app = app_client
        resp = client.get("/api/tasks")
        assert resp.status_code == 200
        assert resp.json() == {"tasks": []}

    def test_create_task(self, app_client):
        client, app = app_client
        resp = client.post("/api/tasks", json={
            "name": "Daily check",
            "task_type": "health_check",
            "schedule": "0 9 * * *",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "created"
        assert "id" in data

    def test_get_task(self, app_client):
        client, app = app_client
        queue = app.state.task_queue
        task_id = queue.add_task("Check", "health_check")
        resp = client.get(f"/api/tasks/{task_id}")
        data = resp.json()
        assert data["task"]["name"] == "Check"
        assert "runs" in data

    def test_get_task_not_found(self, app_client):
        client, app = app_client
        resp = client.get("/api/tasks/999")
        assert resp.status_code == 404

    def test_pause_resume(self, app_client):
        client, app = app_client
        queue = app.state.task_queue
        task_id = queue.add_task("Check", "health_check")

        # Pause
        resp = client.patch(f"/api/tasks/{task_id}", json={"status": "paused"})
        assert resp.status_code == 200
        assert queue.get_task(task_id)["status"] == "paused"

        # Resume
        resp = client.patch(f"/api/tasks/{task_id}", json={"status": "pending"})
        assert resp.status_code == 200
        assert queue.get_task(task_id)["status"] == "pending"

    def test_recent_runs(self, app_client):
        client, app = app_client
        resp = client.get("/api/tasks/runs/recent")
        assert resp.status_code == 200
        assert "runs" in resp.json()


# --- Approval routes ---

class TestApprovalRoutes:
    def test_list_empty(self, app_client):
        client, app = app_client
        resp = client.get("/api/approvals")
        assert resp.status_code == 200
        assert resp.json() == {"approvals": []}

    def test_approve(self, app_client):
        client, app = app_client
        queue = app.state.action_queue
        action_id = queue.add_action(
            business_id=1,
            action_type="send_email",
            description="Send welcome email",
        )
        resp = client.post(f"/api/approvals/{action_id}/approve")
        assert resp.status_code == 200
        assert resp.json()["status"] == "approved"

    def test_deny(self, app_client):
        client, app = app_client
        queue = app.state.action_queue
        action_id = queue.add_action(
            business_id=1,
            action_type="send_email",
            description="Send promo email",
        )
        resp = client.post(
            f"/api/approvals/{action_id}/deny",
            json={"reason": "Not now"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "denied"

    def test_approve_not_found(self, app_client):
        client, app = app_client
        resp = client.post("/api/approvals/999/approve")
        assert resp.status_code == 404

    def test_stats(self, app_client):
        client, app = app_client
        resp = client.get("/api/approvals/stats")
        assert resp.status_code == 200
        assert "stats" in resp.json()


# --- API key auth ---

class TestApiKeyAuth:
    def test_no_key_configured_allows_access(self, app_client):
        client, app = app_client
        resp = client.get("/api/system/status")
        assert resp.status_code == 200

    def test_key_required_when_configured(self, app_client):
        client, app = app_client
        app.state.api_key = "test-secret-key"
        resp = client.get("/api/system/status")
        assert resp.status_code == 401

    def test_correct_key_allows_access(self, app_client):
        client, app = app_client
        app.state.api_key = "test-secret-key"
        resp = client.get(
            "/api/system/status",
            headers={"X-API-Key": "test-secret-key"},
        )
        assert resp.status_code == 200

    def test_wrong_key_denied(self, app_client):
        client, app = app_client
        app.state.api_key = "test-secret-key"
        resp = client.get(
            "/api/system/status",
            headers={"X-API-Key": "wrong"},
        )
        assert resp.status_code == 401


# --- WebSocket chat ---

class TestWebSocketChat:
    def test_ws_connects_and_sends_thinking(self, app_client):
        """WebSocket should connect and send 'thinking' indicator before response."""
        client, app = app_client

        mock_agent = MagicMock()
        mock_agent.run.return_value = "Hello from Merkaba"
        mock_agent.permission_manager = MagicMock()

        with patch("merkaba.agent.Agent", return_value=mock_agent):
            with client.websocket_connect("/ws/chat") as ws:
                ws.send_json({"message": "Hi"})

                # First message should be the thinking indicator
                msg1 = ws.receive_json()
                assert msg1["type"] == "thinking"
                assert msg1["tool"] is None
                assert msg1["status"] == "processing"

                # Second message should be the response
                msg2 = ws.receive_json()
                assert msg2["type"] == "response"
                assert msg2["content"] == "Hello from Merkaba"

    def test_ws_sends_tool_events(self, app_client):
        """WebSocket should relay tool call events as thinking updates."""
        client, app = app_client

        mock_agent = MagicMock()
        mock_agent.permission_manager = MagicMock()

        def fake_run(message, on_tool_call=None):
            if on_tool_call:
                on_tool_call("memory_search", {"query": "test"}, "result")
            return "Done"

        mock_agent.run.side_effect = fake_run

        with patch("merkaba.agent.Agent", return_value=mock_agent):
            with client.websocket_connect("/ws/chat") as ws:
                ws.send_json({"message": "search something"})

                msg1 = ws.receive_json()
                assert msg1["type"] == "thinking"
                assert msg1["tool"] is None

                msg2 = ws.receive_json()
                assert msg2["type"] == "thinking"
                assert msg2["tool"] == "memory_search"

                msg3 = ws.receive_json()
                assert msg3["type"] == "response"

    def test_ws_rejects_without_api_key_when_configured(self, app_client):
        """WebSocket should reject connection when API key is configured but not provided."""
        from starlette.websockets import WebSocketDisconnect

        client, app = app_client
        app.state.api_key = "ws-secret-key"

        mock_agent = MagicMock()
        mock_agent.run.return_value = "Hello"
        mock_agent.permission_manager = MagicMock()

        with patch("merkaba.agent.Agent", return_value=mock_agent):
            with pytest.raises(WebSocketDisconnect) as exc_info:
                with client.websocket_connect("/ws/chat"):
                    pass  # Should not reach here
            assert exc_info.value.code == 4001

    def test_ws_accepts_with_valid_api_key(self, app_client):
        """WebSocket should accept connection when correct API key is provided."""
        client, app = app_client
        app.state.api_key = "ws-secret-key"

        mock_agent = MagicMock()
        mock_agent.run.return_value = "Hello from Merkaba"
        mock_agent.permission_manager = MagicMock()

        with patch("merkaba.agent.Agent", return_value=mock_agent):
            with client.websocket_connect(
                "/ws/chat",
                headers={"X-API-Key": "ws-secret-key"},
            ) as ws:
                ws.send_json({"message": "Hi"})

                msg1 = ws.receive_json()
                assert msg1["type"] == "thinking"

                msg2 = ws.receive_json()
                assert msg2["type"] == "response"
                assert msg2["content"] == "Hello from Merkaba"


# --- Chat session routes ---

class TestChatSessions:
    def test_list_sessions_empty(self, app_client):
        """Listing sessions when conversations dir does not exist returns empty list."""
        client, app = app_client
        with patch("merkaba.web.routes.chat.CONVERSATIONS_DIR", "/nonexistent/path"):
            resp = client.get("/api/chat/sessions")
            assert resp.status_code == 200
            assert resp.json() == {"sessions": []}

    def test_get_session_path_traversal_blocked(self, app_client):
        """Session IDs with special characters should be rejected with 400.

        The regex ``^[\\w\\-]+$`` blocks dots, semicolons, and other non-word
        chars, preventing path traversal (..etc) and command injection (foo;bar).
        IDs containing '/' never reach the handler because FastAPI splits on '/'.
        """
        client, app = app_client
        # Characters blocked by the regex that don't contain '/'
        for bad_id in ["..etc", "foo..bar", "foo;bar", "foo@bar"]:
            resp = client.get(f"/api/chat/sessions/{bad_id}")
            assert resp.status_code == 400, (
                f"Expected 400 for ID '{bad_id}', got {resp.status_code}"
            )

    def test_get_session_not_found(self, app_client):
        """Valid session ID format but no matching file returns 404."""
        client, app = app_client
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("merkaba.web.routes.chat.CONVERSATIONS_DIR", tmpdir):
                resp = client.get("/api/chat/sessions/nonexistent-session-id")
                assert resp.status_code == 404
                assert "not found" in resp.json()["detail"].lower()

    def test_get_session_valid(self, app_client):
        """Creating a session file and loading it back returns correct data."""
        client, app = app_client
        with tempfile.TemporaryDirectory() as tmpdir:
            session_id = "test-session-abc123"
            session_data = {
                "session_id": session_id,
                "messages": [
                    {"role": "user", "content": "Hello"},
                    {"role": "assistant", "content": "Hi there!"},
                ],
                "saved_at": "2026-02-28T12:00:00",
            }
            fpath = os.path.join(tmpdir, f"{session_id}.json")
            with open(fpath, "w") as f:
                json.dump(session_data, f)

            with patch("merkaba.web.routes.chat.CONVERSATIONS_DIR", tmpdir):
                resp = client.get(f"/api/chat/sessions/{session_id}")
                assert resp.status_code == 200
                data = resp.json()
                assert data["session_id"] == session_id
                assert len(data["messages"]) == 2
                assert data["messages"][0]["role"] == "user"
                assert data["messages"][0]["content"] == "Hello"


# --- File upload ---

class TestFileUpload:
    def test_upload_returns_path_and_size(self, app_client):
        """Uploading a file returns its saved path and size."""
        client, app = app_client
        file_content = b"Hello, this is a test file."
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("merkaba.web.routes.chat.UPLOAD_DIR", tmpdir):
                resp = client.post(
                    "/api/upload",
                    files={"file": ("test.txt", file_content, "text/plain")},
                )
                assert resp.status_code == 200
                data = resp.json()
                assert "path" in data
                assert data["path"].startswith(tmpdir)
                assert data["path"].endswith(".txt")
                assert data["filename"] == "test.txt"
                assert data["size"] == len(file_content)
                # Verify the file actually exists on disk
                assert os.path.isfile(data["path"])

    def test_upload_sanitizes_filename(self, app_client):
        """Filenames with path traversal characters are sanitized via os.path.basename."""
        client, app = app_client
        file_content = b"sneaky content"
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("merkaba.web.routes.chat.UPLOAD_DIR", tmpdir):
                resp = client.post(
                    "/api/upload",
                    files={"file": ("../../etc/config.txt", file_content, "text/plain")},
                )
                assert resp.status_code == 200
                data = resp.json()
                # The saved path should be inside the upload dir, not escaped
                saved_path = data["path"]
                assert saved_path.startswith(tmpdir)
                assert os.path.realpath(saved_path).startswith(os.path.realpath(tmpdir))
                # The original filename is returned as-is for display
                assert data["filename"] == "../../etc/config.txt"
                # But the actual file on disk is safely inside tmpdir
                assert os.path.isfile(saved_path)


# --- Business config routes ---

class TestBusinessConfig:
    def test_get_config_returns_defaults(self, app_client):
        """Without any files, config returns builtin defaults."""
        client, app = app_client
        # Create a business first
        store = app.state.memory_store
        store.add_business("Test Biz", "ecommerce")
        resp = client.get("/api/businesses/1/config")
        assert resp.status_code == 200
        data = resp.json()
        assert "soul" in data
        assert "user" in data
        assert data["soul_source"] == "builtin"
        assert data["user_source"] == "builtin"

    def test_get_config_reads_global_files(self, app_client):
        """Config returns content from global SOUL.md/USER.md."""
        client, app = app_client
        store = app.state.memory_store
        store.add_business("Test Biz", "ecommerce")
        merkaba_dir = app.state.merkaba_base_dir
        with open(os.path.join(merkaba_dir, "SOUL.md"), "w") as f:
            f.write("Global soul content")
        resp = client.get("/api/businesses/1/config")
        assert resp.status_code == 200
        data = resp.json()
        assert data["soul"] == "Global soul content"
        assert data["soul_source"] == "global"

    def test_put_config_writes_business_files(self, app_client):
        """PUT config creates per-business SOUL.md and USER.md files."""
        client, app = app_client
        store = app.state.memory_store
        store.add_business("Test Biz", "ecommerce")
        resp = client.put("/api/businesses/1/config", json={
            "soul": "Custom soul for biz 1",
            "user": "Custom user for biz 1",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["soul"] == "Custom soul for biz 1"
        assert data["user"] == "Custom user for biz 1"
        assert data["soul_source"] == "business"
        assert data["user_source"] == "business"
        # Verify files on disk
        merkaba_dir = app.state.merkaba_base_dir
        biz_dir = os.path.join(merkaba_dir, "businesses", "1")
        assert os.path.isfile(os.path.join(biz_dir, "SOUL.md"))
        assert os.path.isfile(os.path.join(biz_dir, "USER.md"))

    def test_put_config_partial_update(self, app_client):
        """PUT with only soul updates soul, leaves user as default."""
        client, app = app_client
        store = app.state.memory_store
        store.add_business("Test Biz", "ecommerce")
        resp = client.put("/api/businesses/1/config", json={
            "soul": "Only soul updated",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["soul"] == "Only soul updated"
        assert data["soul_source"] == "business"
        assert data["user_source"] == "builtin"

    def test_get_config_business_overrides_global(self, app_client):
        """Business-specific file takes priority over global."""
        client, app = app_client
        store = app.state.memory_store
        store.add_business("Test Biz", "ecommerce")
        merkaba_dir = app.state.merkaba_base_dir
        # Write global
        with open(os.path.join(merkaba_dir, "SOUL.md"), "w") as f:
            f.write("Global soul")
        # Write business override
        biz_dir = os.path.join(merkaba_dir, "businesses", "1")
        os.makedirs(biz_dir, exist_ok=True)
        with open(os.path.join(biz_dir, "SOUL.md"), "w") as f:
            f.write("Business 1 soul")
        resp = client.get("/api/businesses/1/config")
        data = resp.json()
        assert data["soul"] == "Business 1 soul"
        assert data["soul_source"] == "business"


# --- Analytics routes ---

class TestAnalytics:
    def test_analytics_overview_empty(self, app_client):
        """Analytics with no data returns empty aggregations."""
        client, app = app_client
        resp = client.get("/api/analytics/overview")
        assert resp.status_code == 200
        data = resp.json()
        assert data["businesses"] == 0
        assert "tasks_by_business" in data
        assert "approvals_summary" in data
        assert "memory_by_business" in data

    def test_analytics_with_business_data(self, app_client):
        """Analytics returns per-business task and memory counts."""
        client, app = app_client
        store = app.state.memory_store
        store.add_business("Biz A", "ecommerce")
        store.add_fact(1, "general", "fact1", "test fact")
        store.add_fact(1, "general", "fact2", "another fact")
        store.add_decision(1, "pricing", "raised price", "market demand")

        resp = client.get("/api/analytics/overview")
        assert resp.status_code == 200
        data = resp.json()
        assert data["businesses"] == 1
        assert "1" in data["memory_by_business"]
        assert data["memory_by_business"]["1"]["facts"] == 2
        assert data["memory_by_business"]["1"]["decisions"] == 1

    def test_analytics_with_days_param(self, app_client):
        """Analytics accepts days query parameter."""
        client, app = app_client
        resp = client.get("/api/analytics/overview?days=7")
        assert resp.status_code == 200

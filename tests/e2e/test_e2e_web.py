# tests/e2e/test_e2e_web.py
"""End-to-end tests for the Mission Control web API endpoints.

Uses real SQLite databases (in temp dirs) and the FastAPI TestClient.
Only the LLM layer is mocked (via global conftest sys.modules trick).
"""

import json
import os
import sqlite3
import sys
from unittest.mock import patch, MagicMock

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


# ---------------------------------------------------------------------------
# Helpers & Fixtures
# ---------------------------------------------------------------------------

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
    """Create a test client with temp databases."""
    memory_db = str(tmp_path / "memory.db")
    tasks_db = str(tmp_path / "tasks.db")
    actions_db = str(tmp_path / "actions.db")
    merkaba_dir = str(tmp_path / "merkaba_home")
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


# ---------------------------------------------------------------------------
# 1. System status
# ---------------------------------------------------------------------------

def test_web_system_status(app_client):
    """GET /api/system/status returns 200 with ollama, databases, and counts keys."""
    client, app = app_client

    resp = client.get("/api/system/status")
    assert resp.status_code == 200

    data = resp.json()
    assert "ollama" in data
    assert "databases" in data
    assert "counts" in data


# ---------------------------------------------------------------------------
# 2. Business CRUD
# ---------------------------------------------------------------------------

def test_web_business_crud(app_client):
    """Create a business via store, then list and fetch it through the API."""
    client, app = app_client
    store = app.state.memory_store

    # Create a business directly via the store
    biz_id = store.add_business("E2E Test Shop", "ecommerce", autonomy_level=3)

    # GET list — should contain the new business
    resp = client.get("/api/businesses")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["businesses"]) == 1
    assert data["businesses"][0]["name"] == "E2E Test Shop"

    # GET single — should return business details and facts
    resp = client.get(f"/api/businesses/{biz_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["business"]["name"] == "E2E Test Shop"
    assert data["business"]["type"] == "ecommerce"
    assert "facts" in data


# ---------------------------------------------------------------------------
# 3. Task CRUD
# ---------------------------------------------------------------------------

def test_web_task_crud(app_client):
    """Create a task via POST, list, fetch, and pause it via PATCH."""
    client, app = app_client

    # POST — create a new task
    resp = client.post("/api/tasks", json={
        "name": "E2E health check",
        "task_type": "health_check",
        "schedule": "0 */6 * * *",
    })
    assert resp.status_code == 200
    create_data = resp.json()
    assert create_data["status"] == "created"
    task_id = create_data["id"]

    # GET list — should contain the new task
    resp = client.get("/api/tasks")
    assert resp.status_code == 200
    tasks = resp.json()["items"]
    assert len(tasks) == 1
    assert tasks[0]["name"] == "E2E health check"

    # GET single — should return task details and runs
    resp = client.get(f"/api/tasks/{task_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["task"]["name"] == "E2E health check"
    assert "runs" in data

    # PATCH — pause the task
    resp = client.patch(f"/api/tasks/{task_id}", json={"status": "paused"})
    assert resp.status_code == 200

    queue = app.state.task_queue
    assert queue.get_task(task_id)["status"] == "paused"


# ---------------------------------------------------------------------------
# 4. Approval workflow
# ---------------------------------------------------------------------------

def test_web_approval_workflow(app_client):
    """Add an action via queue, list it, approve it, and verify status changed."""
    client, app = app_client
    queue = app.state.action_queue

    # Add an action directly via the queue
    action_id = queue.add_action(
        business_id=1,
        action_type="send_email",
        description="Send onboarding email to new customer",
    )

    # GET list — action should appear as pending
    resp = client.get("/api/approvals")
    assert resp.status_code == 200
    approvals = resp.json()["approvals"]
    assert len(approvals) == 1
    assert approvals[0]["action_type"] == "send_email"

    # POST approve
    resp = client.post(f"/api/approvals/{action_id}/approve", json={})
    assert resp.status_code == 200
    assert resp.json()["status"] == "approved"

    # Verify status changed in the queue
    action = queue.get_action(action_id)
    assert action["status"] == "approved"


# ---------------------------------------------------------------------------
# 5. Memory search
# ---------------------------------------------------------------------------

def test_web_memory_search(app_client):
    """GET /api/memory/search echoes the query and returns results."""
    client, app = app_client

    resp = client.get("/api/memory/search?q=test")
    assert resp.status_code == 200

    data = resp.json()
    assert data["query"] == "test"
    assert "results" in data


# ---------------------------------------------------------------------------
# 6. Analytics overview
# ---------------------------------------------------------------------------

def test_web_analytics_overview(app_client):
    """GET /api/analytics/overview returns expected aggregation keys."""
    client, app = app_client

    resp = client.get("/api/analytics/overview")
    assert resp.status_code == 200

    data = resp.json()
    assert "businesses" in data
    assert "tasks_by_business" in data
    assert "approvals_summary" in data
    assert "memory_by_business" in data


# ---------------------------------------------------------------------------
# 7. API key enforcement
# ---------------------------------------------------------------------------

def test_web_api_key_enforcement(app_client):
    """When api_key is set, requests without the key get 401; with it get 200."""
    client, app = app_client

    # Without a key configured, access is open
    resp = client.get("/api/system/status")
    assert resp.status_code == 200

    # Configure a key
    app.state.api_key = "e2e-secret-key"

    # Request without key should be rejected
    resp = client.get("/api/system/status")
    assert resp.status_code == 401

    # Request with correct key should succeed
    resp = client.get(
        "/api/system/status",
        headers={"X-API-Key": "e2e-secret-key"},
    )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 8. WebSocket chat
# ---------------------------------------------------------------------------

def test_web_websocket_chat(app_client):
    """WebSocket connect, send a message, receive thinking + response messages."""
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

            # Second message should be the response
            msg2 = ws.receive_json()
            assert msg2["type"] == "response"
            assert msg2["content"] == "Hello from Merkaba"


# ---------------------------------------------------------------------------
# 8b. WebSocket chat — agent error returns generic message (C1)
# ---------------------------------------------------------------------------

def test_web_websocket_chat_error_is_sanitized(app_client):
    """WebSocket agent error sends a generic message, not the raw exception text.

    Verifies finding C1: str(e) must not be forwarded to the client. The
    content must not contain file paths, tracebacks, or internal module names.
    """
    client, app = app_client

    internal_error = RuntimeError(
        "Traceback (most recent call last):\n"
        "  File /Users/cevin/src/merkaba/src/merkaba/agent.py, line 42\n"
        "sqlite3.OperationalError: database is locked: /home/user/.merkaba/memory.db"
    )

    mock_agent = MagicMock()
    mock_agent.run.side_effect = internal_error
    mock_agent.permission_manager = MagicMock()

    with patch("merkaba.agent.Agent", return_value=mock_agent):
        with client.websocket_connect("/ws/chat") as ws:
            ws.send_json({"message": "trigger error"})

            # First message is the thinking indicator
            msg1 = ws.receive_json()
            assert msg1["type"] == "thinking"

            # Second message must be a generic error — NOT the raw exception
            msg2 = ws.receive_json()
            assert msg2["type"] == "error"

            content = msg2["content"]
            # Must be the sanitized generic message
            assert "internal error" in content.lower() or "please try again" in content.lower()
            # Must NOT leak any internal details
            assert "Traceback" not in content
            assert "merkaba" not in content
            assert "/Users/" not in content
            assert "/home/" not in content
            assert "sqlite3" not in content
            assert ".db" not in content
            assert "agent.py" not in content


# ---------------------------------------------------------------------------
# 9. File upload — valid extension succeeds
# ---------------------------------------------------------------------------

def test_web_upload_valid_file(app_client, tmp_path):
    """POST /api/upload with an allowed extension returns 200 and file metadata."""
    client, app = app_client
    upload_dir = str(tmp_path / "uploads")

    with patch("merkaba.web.routes.chat.UPLOAD_DIR", upload_dir):
        resp = client.post(
            "/api/upload",
            files={"file": ("notes.txt", b"Hello world", "text/plain")},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["filename"] == "notes.txt"
    assert data["size"] == len(b"Hello world")
    assert data["path"].endswith(".txt")
    # Verify the file was actually written
    assert os.path.isfile(data["path"])


# ---------------------------------------------------------------------------
# 10. File upload — disallowed extension returns 400
# ---------------------------------------------------------------------------

def test_web_upload_bad_extension(app_client):
    """POST /api/upload with a disallowed extension (.exe) returns 400."""
    client, app = app_client

    resp = client.post(
        "/api/upload",
        files={"file": ("malware.exe", b"MZ\x90\x00", "application/octet-stream")},
    )

    assert resp.status_code == 400
    assert "not allowed" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# 11. File upload — oversized file returns 413
# ---------------------------------------------------------------------------

def test_web_upload_oversized(app_client):
    """POST /api/upload with content exceeding MAX_UPLOAD_SIZE returns 413."""
    client, app = app_client

    # Create content just over the 10 MB limit
    oversized_content = b"x" * (10 * 1024 * 1024 + 1)

    resp = client.post(
        "/api/upload",
        files={"file": ("big.txt", oversized_content, "text/plain")},
    )

    assert resp.status_code == 413
    assert "exceeds maximum" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# 12. Deny action with reason
# ---------------------------------------------------------------------------

def test_deny_with_reason(app_client):
    """POST /api/approvals/{id}/deny with a reason stores the reason in the DB."""
    client, app = app_client
    queue = app.state.action_queue

    action_id = queue.add_action(
        business_id=1,
        action_type="delete_record",
        description="Delete a customer record",
    )

    resp = client.post(
        f"/api/approvals/{action_id}/deny",
        json={"reason": "violates retention policy"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "denied"
    assert data["reason"] == "violates retention policy"

    # Verify reason persisted in DB
    action = queue.get_action(action_id)
    assert action["status"] == "denied"
    assert action["reason"] == "violates retention policy"


# ---------------------------------------------------------------------------
# 13. Deny action without reason (backward-compat)
# ---------------------------------------------------------------------------

def test_deny_without_reason(app_client):
    """POST /api/approvals/{id}/deny with empty body still works (reason is None)."""
    client, app = app_client
    queue = app.state.action_queue

    action_id = queue.add_action(
        business_id=1,
        action_type="send_email",
        description="Send marketing email",
    )

    # No JSON body at all — FastAPI should use the default (reason=None)
    resp = client.post(f"/api/approvals/{action_id}/deny", json={})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "denied"
    assert data["reason"] is None

    action = queue.get_action(action_id)
    assert action["status"] == "denied"
    assert action["reason"] is None


# ---------------------------------------------------------------------------
# 14. Rate limit returns Retry-After header
# ---------------------------------------------------------------------------

def test_rate_limit_returns_retry_after(app_client):
    """When the approval rate limit is exceeded, the response is 429 with Retry-After."""
    client, app = app_client
    queue = app.state.action_queue

    from merkaba.approval.secure import RateLimitConfig, SecureApprovalManager
    from unittest.mock import patch

    # Set a tight rate limit: max 1 approval per 60-second window
    tight_config = RateLimitConfig(max_approvals=1, window_seconds=60)
    tight_manager = SecureApprovalManager(action_queue=queue, rate_limit=tight_config)

    # Approve one action directly via the manager to fill the bucket
    fill_id = queue.add_action(
        business_id=1, action_type="test", description="Fill bucket", autonomy_level=1
    )
    tight_manager.approve(fill_id, decided_by="test")

    # Patch SecureApprovalManager.from_config to return our tight manager.
    # The approve endpoint imports SecureApprovalManager lazily from
    # merkaba.approval.secure, so we patch it there.
    with patch(
        "merkaba.approval.secure.SecureApprovalManager.from_config",
        return_value=tight_manager,
    ):
        blocked_id = queue.add_action(
            business_id=1, action_type="test", description="Blocked", autonomy_level=1
        )
        resp = client.post(f"/api/approvals/{blocked_id}/approve", json={})

    assert resp.status_code == 429
    assert resp.json()["detail"] == "Rate limit exceeded"
    assert "retry-after" in resp.headers
    assert resp.headers["retry-after"] == "60"

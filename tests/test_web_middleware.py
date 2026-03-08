"""Tests for SecurityHeadersMiddleware."""
import os
import sys
import tempfile
from unittest.mock import MagicMock

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


@pytest.fixture
def app_client(make_store):
    """Create a test client with temp databases."""
    with tempfile.TemporaryDirectory() as tmpdir:
        memory_db = os.path.join(tmpdir, "memory.db")
        tasks_db = os.path.join(tmpdir, "tasks.db")
        actions_db = os.path.join(tmpdir, "actions.db")
        merkaba_dir = os.path.join(tmpdir, "merkaba_home")
        os.makedirs(merkaba_dir, exist_ok=True)

        overrides = {
            "memory_store": make_store(MemoryStore, memory_db),
            "task_queue": make_store(TaskQueue, tasks_db),
            "action_queue": make_store(ActionQueue, actions_db),
            "merkaba_base_dir": merkaba_dir,
        }

        app = create_app(db_overrides=overrides)

        with TestClient(app, raise_server_exceptions=False) as client:
            yield client


class TestSecurityHeaders:
    def test_security_headers_present(self, app_client):
        """All five security headers must be present on every response."""
        resp = app_client.get("/api/system/status")
        assert resp.status_code == 200

        assert resp.headers["X-Content-Type-Options"] == "nosniff"
        assert resp.headers["X-Frame-Options"] == "DENY"
        assert resp.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
        assert resp.headers["Permissions-Policy"] == "camera=(), microphone=(), geolocation=()"
        assert "Content-Security-Policy" in resp.headers

    def test_csp_allows_websocket(self, app_client):
        """The Content-Security-Policy must permit ws: and wss: connections."""
        resp = app_client.get("/api/system/status")
        csp = resp.headers["Content-Security-Policy"]

        assert "ws:" in csp
        assert "wss:" in csp

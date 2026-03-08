"""Unit tests for Mission Control helper functions."""

import asyncio
import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# Stub out heavy deps before importing
if "ollama" not in sys.modules:
    sys.modules["ollama"] = MagicMock()


class TestGetRecentActivity:
    """Tests for _get_recent_activity helper."""

    @pytest.fixture(autouse=True)
    def _import(self):
        from merkaba.web.routes.control import _get_recent_activity

        self._get_recent_activity = _get_recent_activity

    def test_returns_empty_when_base_dir_none(self):
        assert self._get_recent_activity(None) == []

    def test_returns_empty_when_dir_missing(self, tmp_path):
        assert self._get_recent_activity(str(tmp_path / "nope")) == []

    def test_sorts_by_filename_descending(self, tmp_path):
        conv_dir = tmp_path / "conversations"
        conv_dir.mkdir()
        for name in ["20260101-100000", "20260103-100000", "20260102-100000"]:
            (conv_dir / f"{name}.json").write_text(
                json.dumps(
                    {
                        "session_id": name,
                        "messages": [{"role": "user", "content": name}],
                        "saved_at": "2026-01-01T00:00:00",
                    }
                )
            )
        result = self._get_recent_activity(str(tmp_path))
        ids = [r["session_id"] for r in result]
        assert ids == ["20260103-100000", "20260102-100000", "20260101-100000"]

    def test_respects_custom_limit(self, tmp_path):
        conv_dir = tmp_path / "conversations"
        conv_dir.mkdir()
        for i in range(5):
            (conv_dir / f"2026010{i}-100000.json").write_text(
                json.dumps(
                    {
                        "session_id": f"2026010{i}-100000",
                        "messages": [{"role": "user", "content": f"msg {i}"}],
                        "saved_at": "2026-01-01T00:00:00",
                    }
                )
            )
        result = self._get_recent_activity(str(tmp_path), limit=2)
        assert len(result) == 2

    def test_skips_malformed_json(self, tmp_path):
        conv_dir = tmp_path / "conversations"
        conv_dir.mkdir()
        (conv_dir / "bad.json").write_text("{not valid json!!!")
        result = self._get_recent_activity(str(tmp_path))
        assert result == []

    def test_skips_non_json_files(self, tmp_path):
        conv_dir = tmp_path / "conversations"
        conv_dir.mkdir()
        (conv_dir / "readme.txt").write_text("not a convo")
        (conv_dir / "valid.json").write_text(
            json.dumps(
                {
                    "session_id": "valid",
                    "messages": [{"role": "user", "content": "hi"}],
                    "saved_at": "2026-01-01T00:00:00",
                }
            )
        )
        result = self._get_recent_activity(str(tmp_path))
        assert len(result) == 1
        assert result[0]["session_id"] == "valid"


class TestWorkerConstantsConsistency:
    """Tests ensuring WORKER_DESCRIPTIONS and WORKER_SCHEDULES stay consistent."""

    def test_all_scheduled_workers_have_descriptions(self):
        from merkaba.web.routes.control import WORKER_DESCRIPTIONS, WORKER_SCHEDULES

        for key in WORKER_SCHEDULES:
            assert key in WORKER_DESCRIPTIONS, (
                f"{key} in WORKER_SCHEDULES but not WORKER_DESCRIPTIONS"
            )

    def test_all_descriptions_non_empty(self):
        from merkaba.web.routes.control import WORKER_DESCRIPTIONS

        for key, desc in WORKER_DESCRIPTIONS.items():
            assert desc, f"WORKER_DESCRIPTIONS['{key}'] is empty"

    def test_schedules_are_valid_cron(self):
        from croniter import croniter

        from merkaba.web.routes.control import WORKER_SCHEDULES

        for key, cron in WORKER_SCHEDULES.items():
            assert croniter.is_valid(cron), f"Invalid cron for '{key}': {cron}"


class TestBuildKanbanUnit:
    """Tests for _build_kanban logic with mocked queues."""

    @pytest.fixture
    def mock_conn(self, tmp_path):
        """Create a mock HTTPConnection with real SQLite-backed queues."""
        import sqlite3

        from merkaba.approval.queue import ActionQueue
        from merkaba.orchestration.queue import TaskQueue

        def _make(cls, path):
            obj = object.__new__(cls)
            obj.db_path = path
            obj._conn = sqlite3.connect(path, check_same_thread=False)
            obj._conn.row_factory = sqlite3.Row
            obj._conn.execute("PRAGMA foreign_keys = ON")
            obj._create_tables()
            return obj

        tq = _make(TaskQueue, str(tmp_path / "tasks.db"))
        aq = _make(ActionQueue, str(tmp_path / "actions.db"))

        conn = MagicMock()
        conn.app.state.task_queue = tq
        conn.app.state.action_queue = aq
        yield conn
        tq.close()
        aq.close()

    def test_empty_queues_returns_all_empty_columns(self, mock_conn):
        from merkaba.web.routes.control import _build_kanban

        result = _build_kanban(mock_conn)
        assert result["queued"] == []
        assert result["awaiting_approval"] == []
        assert result["running"] == []
        assert result["completed"] == []
        assert result["failed"] == []

    def test_approval_card_has_required_fields(self, mock_conn):
        from merkaba.web.routes.control import _build_kanban

        aq = mock_conn.app.state.action_queue
        aq.add_action(business_id=1, action_type="post", description="Post item")
        result = _build_kanban(mock_conn)
        card = result["awaiting_approval"][0]
        assert "id" in card
        assert "business_id" in card
        assert "action_type" in card
        assert "description" in card
        assert "created_at" in card

    def test_completed_card_has_task_fields(self, mock_conn):
        from merkaba.web.routes.control import _build_kanban

        tq = mock_conn.app.state.task_queue
        tid = tq.add_task("Test", "health_check")
        rid = tq.start_run(tid)
        tq.finish_run(rid, "success", result={"ok": True})
        result = _build_kanban(mock_conn)
        card = result["completed"][0]
        assert card["name"] == "Test"
        assert card["task_type"] == "health_check"

    def test_failed_card_has_error_field(self, mock_conn):
        from merkaba.web.routes.control import _build_kanban

        tq = mock_conn.app.state.task_queue
        tid = tq.add_task("Fail", "health_check")
        rid = tq.start_run(tid)
        tq.finish_run(rid, "failed", error="timeout")
        result = _build_kanban(mock_conn)
        card = result["failed"][0]
        assert card["error"] == "timeout"


class TestHeartbeatNonBlocking:
    """Verify that _build_state and _build_kanban are called via asyncio.to_thread
    in async contexts so they don't block the event loop."""

    def test_get_control_state_uses_to_thread(self):
        """The /api/control/state endpoint should offload _build_state to a thread."""
        from merkaba.web.routes.control import get_control_state

        fake_state = {"type": "state_update", "system": {}}
        request = MagicMock()

        with patch(
            "merkaba.web.routes.control._build_state", return_value=fake_state
        ) as mock_build, patch(
            "merkaba.web.routes.control.asyncio"
        ) as mock_asyncio:
            # Make to_thread return a coroutine that resolves to fake_state
            async def fake_to_thread(fn, *args):
                return fn(*args)

            mock_asyncio.to_thread = fake_to_thread

            result = asyncio.get_event_loop().run_until_complete(
                get_control_state(request)
            )
            assert result == fake_state
            mock_build.assert_called_once_with(request)

    def test_get_kanban_state_uses_to_thread(self):
        """The /api/control/kanban endpoint should offload _build_kanban to a thread."""
        from merkaba.web.routes.control import get_kanban_state

        fake_kanban = {"queued": [], "running": []}
        request = MagicMock()

        with patch(
            "merkaba.web.routes.control._build_kanban", return_value=fake_kanban
        ) as mock_build, patch(
            "merkaba.web.routes.control.asyncio"
        ) as mock_asyncio:
            async def fake_to_thread(fn, *args):
                return fn(*args)

            mock_asyncio.to_thread = fake_to_thread

            result = asyncio.get_event_loop().run_until_complete(
                get_kanban_state(request)
            )
            assert result == fake_kanban
            mock_build.assert_called_once_with(request)

    def test_build_state_called_via_to_thread_in_heartbeat(self):
        """Verify the heartbeat_loop source code uses asyncio.to_thread for _build_state."""
        import inspect

        from merkaba.web.routes.control import websocket_control

        source = inspect.getsource(websocket_control)
        # The heartbeat loop should use asyncio.to_thread for _build_state
        assert "asyncio.to_thread(_build_state" in source, (
            "_build_state should be called via asyncio.to_thread in the heartbeat loop"
        )
        # The heartbeat loop should use asyncio.to_thread for _build_kanban
        assert "asyncio.to_thread(_build_kanban" in source, (
            "_build_kanban should be called via asyncio.to_thread in the heartbeat loop"
        )

    def test_build_state_not_called_synchronously_in_async_functions(self):
        """Ensure no async function calls _build_state synchronously (without to_thread)."""
        import inspect
        import re

        from merkaba.web.routes import control

        source = inspect.getsource(control)

        # Find all lines with _build_state calls
        for i, line in enumerate(source.splitlines(), 1):
            stripped = line.strip()
            # Skip comments and the function definition itself
            if stripped.startswith("#") or stripped.startswith("def _build_state"):
                continue
            if "_build_state(" in stripped:
                # Must be either: the function definition, or called via to_thread
                is_def = "def _build_state" in stripped
                is_to_thread = "to_thread(_build_state" in stripped
                assert is_def or is_to_thread, (
                    f"Line {i}: _build_state called synchronously in async context: {stripped!r}"
                )

    def test_build_kanban_not_called_synchronously_in_async_functions(self):
        """Ensure no async function calls _build_kanban synchronously (without to_thread)."""
        import inspect

        from merkaba.web.routes import control

        source = inspect.getsource(control)

        for i, line in enumerate(source.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith("def _build_kanban"):
                continue
            if "_build_kanban(" in stripped:
                is_def = "def _build_kanban" in stripped
                is_to_thread = "to_thread(_build_kanban" in stripped
                assert is_def or is_to_thread, (
                    f"Line {i}: _build_kanban called synchronously in async context: {stripped!r}"
                )


class TestWebSocketChannelValidation:
    """Tests for WebSocket subscribe/unsubscribe channel validation."""

    def test_valid_channels_constant_defined(self):
        from merkaba.web.routes.control import VALID_CHANNELS

        assert "diagnostics" in VALID_CHANNELS
        assert "kanban" in VALID_CHANNELS

    def test_ws_accepts_valid_channel(self):
        """Subscribe to 'diagnostics' — should be accepted without error."""
        from merkaba.web.routes.control import VALID_CHANNELS

        # Validate the guard logic used in receive_loop
        channel = "diagnostics"
        assert channel in VALID_CHANNELS

        channel = "kanban"
        assert channel in VALID_CHANNELS

    def test_ws_rejects_unknown_channel(self):
        """Unknown channel name should not be in VALID_CHANNELS."""
        from merkaba.web.routes.control import VALID_CHANNELS

        assert "bogus" not in VALID_CHANNELS
        assert "nonexistent" not in VALID_CHANNELS
        assert "" not in VALID_CHANNELS

    def test_receive_loop_validates_subscribe_channel(self):
        """Verify the receive_loop source code checks VALID_CHANNELS on subscribe."""
        import inspect

        from merkaba.web.routes.control import websocket_control

        source = inspect.getsource(websocket_control)
        assert "VALID_CHANNELS" in source, (
            "websocket_control should check VALID_CHANNELS for subscribe/unsubscribe"
        )
        assert '"Unknown channel:' in source or "'Unknown channel:" in source, (
            "websocket_control should send an error message for unknown channels"
        )


class TestChangeModelUsesMerkabaHome:
    """Verify the /model endpoint respects MERKABA_HOME instead of hardcoding ~/.merkaba."""

    def test_merkaba_home_respected_in_config_endpoint(self, tmp_path):
        """When MERKABA_HOME is set, the change_model endpoint should write config there."""
        import asyncio

        config_dir = tmp_path / "custom_home"
        config_dir.mkdir()
        config_file = config_dir / "config.json"
        config_file.write_text(json.dumps({"models": {"complex": "old-model"}}))

        request = MagicMock()
        request.app.state.merkaba_base_dir = None

        with patch.dict(os.environ, {"MERKABA_HOME": str(config_dir)}):
            from merkaba.web.routes.control import ModelChangeRequest, change_model

            body = ModelChangeRequest(agent="merkaba-prime", model="new-model")
            result = asyncio.get_event_loop().run_until_complete(
                change_model(body, request)
            )

        assert result["model"] == "new-model"
        # Verify config was written to MERKABA_HOME, not ~/.merkaba
        written = json.loads(config_file.read_text())
        assert written["models"]["complex"] == "new-model"


class TestBuildStateNoNPlusOne:
    """Verify _build_state uses batch queries instead of per-worker N+1 loops."""

    @pytest.fixture
    def mock_conn(self, tmp_path):
        """Create a mock HTTPConnection with real SQLite-backed queues and mock stores."""
        import sqlite3

        from merkaba.approval.queue import ActionQueue
        from merkaba.orchestration.queue import TaskQueue

        def _make(cls, path):
            obj = object.__new__(cls)
            obj.db_path = path
            obj._conn = sqlite3.connect(path, check_same_thread=False)
            obj._conn.row_factory = sqlite3.Row
            obj._conn.execute("PRAGMA foreign_keys = ON")
            obj._create_tables()
            return obj

        tq = _make(TaskQueue, str(tmp_path / "tasks.db"))
        aq = _make(ActionQueue, str(tmp_path / "actions.db"))

        memory_store = MagicMock()
        memory_store.count_facts.return_value = 0

        conn = MagicMock()
        conn.app.state.task_queue = tq
        conn.app.state.action_queue = aq
        conn.app.state.memory_store = memory_store
        conn.app.state.merkaba_base_dir = None
        yield conn
        tq.close()
        aq.close()

    def test_build_state_query_count_is_constant(self, mock_conn):
        """_build_state should use O(1) queries, not O(n) per worker.

        We seed 10 tasks with multiple runs each, then instrument the DB
        connection to count SELECT queries issued during _build_state.
        The count should be constant regardless of the number of workers.
        """
        from merkaba.web.routes.control import _build_state

        tq = mock_conn.app.state.task_queue

        # Create tasks for each registered worker type, plus extras
        worker_types = []
        for i in range(10):
            wtype = f"worker_{i}"
            worker_types.append(wtype)
            tid = tq.add_task(f"Task {i}", wtype)
            for _ in range(3):
                rid = tq.start_run(tid)
                tq.finish_run(rid, "success")

        # Patch WORKER_REGISTRY to include our test workers
        fake_registry = {}
        for wtype in worker_types:
            fake_cls = type(f"{wtype.title()}Worker", (), {"__name__": f"{wtype.title()}Worker"})
            fake_registry[wtype] = fake_cls

        # Use SQLite's trace callback to count SELECT queries
        select_queries = []

        def trace_callback(statement):
            if statement.strip().upper().startswith("SELECT"):
                select_queries.append(statement)

        tq._conn.set_trace_callback(trace_callback)

        with patch("merkaba.orchestration.workers.WORKER_REGISTRY", fake_registry):
            result = _build_state(mock_conn)

        tq._conn.set_trace_callback(None)

        # With 10 workers, old code would issue 20+ SELECT queries (2 per worker).
        # New code should issue a fixed number regardless of worker count.
        # We allow a generous ceiling: list_tasks (1) + get_runs_for_tasks (1) +
        # count_facts x2 + pending_count + list_tasks(status=running) = ~6
        assert len(select_queries) <= 8, (
            f"Expected O(1) queries but got {len(select_queries)} SELECTs for 10 workers. "
            f"This suggests an N+1 query pattern. Queries: {select_queries}"
        )

        # Verify the response still has all workers with run history
        assert len(result["workers"]) == 10
        for w in result["workers"]:
            assert "run_history" in w
            assert len(w["run_history"]) == 3

    def test_build_state_uses_get_runs_for_tasks(self):
        """_build_state source should call get_runs_for_tasks, not get_runs in a loop."""
        import inspect

        from merkaba.web.routes.control import _build_state

        source = inspect.getsource(_build_state)
        assert "get_runs_for_tasks" in source, (
            "_build_state should use batch get_runs_for_tasks() instead of per-worker get_runs()"
        )
        # Should NOT have the N+1 pattern of calling get_runs inside a loop
        # (get_runs with a single task_id arg inside the worker loop)
        lines = source.split("\n")
        in_worker_loop = False
        for line in lines:
            stripped = line.strip()
            if "for task_type, worker_cls" in stripped:
                in_worker_loop = True
            if in_worker_loop and "get_runs(" in stripped and "get_runs_for_tasks" not in stripped:
                pytest.fail(
                    f"Found per-worker get_runs() call inside worker loop: {stripped!r}"
                )

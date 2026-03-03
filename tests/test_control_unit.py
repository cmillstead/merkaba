"""Unit tests for Mission Control helper functions."""

import json
import os
import sys
from unittest.mock import MagicMock

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

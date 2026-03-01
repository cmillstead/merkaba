# tests/test_cli_tasks.py
"""Tests for CLI tasks and scheduler commands."""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

try:
    import keyring.errors
    HAS_DEPS = True
except ImportError:
    HAS_DEPS = False

pytestmark = pytest.mark.skipif(not HAS_DEPS, reason="Missing keyring")

# Mock problematic modules before importing merkaba.cli
for _mod in ("ollama", "telegram", "telegram.ext"):
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

from merkaba.cli import app

runner = CliRunner()


@pytest.fixture()
def temp_dbs(tmp_path):
    """Patch DB paths to use temp directory."""
    tasks_db = str(tmp_path / "tasks.db")
    memory_db = str(tmp_path / "memory.db")
    actions_db = str(tmp_path / "actions.db")
    with patch("merkaba.orchestration.queue.TaskQueue.__init__", _make_patched_init(tasks_db, "merkaba.orchestration.queue.TaskQueue")), \
         patch("merkaba.memory.store.MemoryStore.__init__", _make_patched_init(memory_db, "merkaba.memory.store.MemoryStore")), \
         patch("merkaba.approval.queue.ActionQueue.__init__", _make_patched_init(actions_db, "merkaba.approval.queue.ActionQueue")):
        yield tmp_path


def _make_patched_init(db_path, class_path):
    """Create a patched __init__ that uses a temp DB path."""
    def patched_init(self, **kwargs):
        self.db_path = db_path
        import sqlite3
        db_dir = os.path.dirname(self.db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._create_tables()
    return patched_init


# --- tasks list ---

def test_tasks_list_empty(temp_dbs):
    result = runner.invoke(app, ["tasks", "list"])
    assert result.exit_code == 0
    assert "no tasks" in result.output.lower()


def test_tasks_list_with_entries(temp_dbs):
    # Add a task first
    runner.invoke(app, ["tasks", "add", "--name", "Daily Research", "--type", "research"])
    result = runner.invoke(app, ["tasks", "list"])
    assert result.exit_code == 0
    assert "Daily Research" in result.output


def test_tasks_list_status_filter(temp_dbs):
    runner.invoke(app, ["tasks", "add", "--name", "Task A", "--type", "research"])
    result = runner.invoke(app, ["tasks", "list", "--status", "paused"])
    assert result.exit_code == 0
    assert "no tasks" in result.output.lower()


# --- tasks add ---

def test_tasks_add(temp_dbs):
    result = runner.invoke(app, ["tasks", "add", "--name", "New Task", "--type", "content"])
    assert result.exit_code == 0
    assert "task created" in result.output.lower()
    assert "New Task" in result.output


def test_tasks_add_with_schedule(temp_dbs):
    result = runner.invoke(app, ["tasks", "add", "--name", "Scheduled", "--type", "research", "--schedule", "0 9 * * *"])
    assert result.exit_code == 0
    assert "0 9 * * *" in result.output


def test_tasks_add_with_business(temp_dbs):
    result = runner.invoke(app, ["tasks", "add", "--name", "Biz Task", "--type", "ecommerce", "--business", "1"])
    assert result.exit_code == 0
    assert "task created" in result.output.lower()


# --- tasks pause ---

def test_tasks_pause(temp_dbs):
    runner.invoke(app, ["tasks", "add", "--name", "Pausable", "--type", "research"])
    result = runner.invoke(app, ["tasks", "pause", "1"])
    assert result.exit_code == 0
    assert "paused" in result.output.lower()


def test_tasks_pause_not_found(temp_dbs):
    result = runner.invoke(app, ["tasks", "pause", "999"])
    assert result.exit_code == 1


# --- tasks resume ---

def test_tasks_resume(temp_dbs):
    runner.invoke(app, ["tasks", "add", "--name", "Resumable", "--type", "research"])
    runner.invoke(app, ["tasks", "pause", "1"])
    result = runner.invoke(app, ["tasks", "resume", "1"])
    assert result.exit_code == 0
    assert "resumed" in result.output.lower()


def test_tasks_resume_not_found(temp_dbs):
    result = runner.invoke(app, ["tasks", "resume", "999"])
    assert result.exit_code == 1


# --- tasks runs ---

def test_tasks_runs_empty(temp_dbs):
    runner.invoke(app, ["tasks", "add", "--name", "No Runs", "--type", "research"])
    result = runner.invoke(app, ["tasks", "runs", "1"])
    assert result.exit_code == 0
    assert "no runs" in result.output.lower()


def test_tasks_runs_not_found(temp_dbs):
    result = runner.invoke(app, ["tasks", "runs", "999"])
    assert result.exit_code == 1


# --- scheduler workers ---

def test_scheduler_workers():
    result = runner.invoke(app, ["scheduler", "workers"])
    assert result.exit_code == 0
    # Should either show workers or "no workers"
    assert "worker" in result.output.lower() or "no workers" in result.output.lower()


# --- scheduler run ---

def test_scheduler_run_no_due(temp_dbs):
    with patch("merkaba.orchestration.supervisor.Supervisor.__init__", return_value=None), \
         patch("merkaba.orchestration.supervisor.Supervisor.close"), \
         patch("merkaba.orchestration.scheduler.Scheduler.tick", return_value=[]):
        result = runner.invoke(app, ["scheduler", "run"])
    assert result.exit_code == 0
    assert "no due" in result.output.lower()


def test_scheduler_run_with_due(temp_dbs):
    due_tasks = [{"id": 1, "name": "Daily Check"}]
    with patch("merkaba.orchestration.supervisor.Supervisor.__init__", return_value=None), \
         patch("merkaba.orchestration.supervisor.Supervisor.close"), \
         patch("merkaba.orchestration.scheduler.Scheduler.tick", return_value=due_tasks):
        result = runner.invoke(app, ["scheduler", "run"])
    assert result.exit_code == 0
    assert "1" in result.output
    assert "Daily Check" in result.output

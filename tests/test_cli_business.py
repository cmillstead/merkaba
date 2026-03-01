# tests/test_cli_business.py
import os
import sys
import tempfile
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
    memory_db = str(tmp_path / "memory.db")
    tasks_db = str(tmp_path / "tasks.db")
    actions_db = str(tmp_path / "actions.db")
    with patch("merkaba.memory.store.MemoryStore.__init__", _make_patched_init(memory_db, "merkaba.memory.store.MemoryStore")), \
         patch("merkaba.orchestration.queue.TaskQueue.__init__", _make_patched_init(tasks_db, "merkaba.orchestration.queue.TaskQueue")), \
         patch("merkaba.approval.queue.ActionQueue.__init__", _make_patched_init(actions_db, "merkaba.approval.queue.ActionQueue")):
        yield tmp_path


def _make_patched_init(db_path, class_path):
    """Create a patched __init__ that uses a temp DB path."""
    def patched_init(self, **kwargs):
        import importlib
        module_path, class_name = class_path.rsplit(".", 1)
        mod = importlib.import_module(module_path)
        cls = getattr(mod, class_name)
        # Call original __post_init__ logic with temp path
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


# --- business add ---

def test_business_add(temp_dbs):
    result = runner.invoke(app, ["business", "add", "--name", "Test Shop", "--type", "ecommerce"])
    assert result.exit_code == 0
    assert "created" in result.output.lower()
    assert "Test Shop" in result.output


def test_business_add_invalid_type(temp_dbs):
    result = runner.invoke(app, ["business", "add", "--name", "Bad", "--type", "invalid"])
    assert result.exit_code == 1


def test_business_add_all_types(temp_dbs):
    for biz_type in ("ecommerce", "content", "saas"):
        result = runner.invoke(app, ["business", "add", "--name", f"Biz {biz_type}", "--type", biz_type])
        assert result.exit_code == 0


# --- business list ---

def test_business_list_empty(temp_dbs):
    result = runner.invoke(app, ["business", "list"])
    assert result.exit_code == 0
    assert "no businesses" in result.output.lower()


def test_business_list_with_entries(temp_dbs):
    runner.invoke(app, ["business", "add", "--name", "Shop A", "--type", "ecommerce"])
    runner.invoke(app, ["business", "add", "--name", "Blog B", "--type", "content"])
    result = runner.invoke(app, ["business", "list"])
    assert result.exit_code == 0
    assert "Shop A" in result.output
    assert "Blog B" in result.output


# --- business show ---

def test_business_show(temp_dbs):
    runner.invoke(app, ["business", "add", "--name", "My Shop", "--type", "ecommerce"])
    result = runner.invoke(app, ["business", "show", "1"])
    assert result.exit_code == 0
    assert "My Shop" in result.output
    assert "ecommerce" in result.output


def test_business_show_not_found(temp_dbs):
    result = runner.invoke(app, ["business", "show", "999"])
    assert result.exit_code == 1


# --- business update ---

def test_business_update(temp_dbs):
    runner.invoke(app, ["business", "add", "--name", "Old Name", "--type", "ecommerce"])
    result = runner.invoke(app, ["business", "update", "1", "--name", "New Name"])
    assert result.exit_code == 0
    assert "updated" in result.output.lower()

    # Verify the update
    show_result = runner.invoke(app, ["business", "show", "1"])
    assert "New Name" in show_result.output


def test_business_update_not_found(temp_dbs):
    result = runner.invoke(app, ["business", "update", "999", "--name", "Ghost"])
    assert result.exit_code == 1


def test_business_update_nothing(temp_dbs):
    runner.invoke(app, ["business", "add", "--name", "Shop", "--type", "ecommerce"])
    result = runner.invoke(app, ["business", "update", "1"])
    assert result.exit_code == 0
    assert "nothing" in result.output.lower()


# --- business dashboard ---

def test_business_dashboard(temp_dbs):
    runner.invoke(app, ["business", "add", "--name", "Dashboard Shop", "--type", "ecommerce"])
    result = runner.invoke(app, ["business", "dashboard", "1"])
    assert result.exit_code == 0
    assert "Dashboard Shop" in result.output
    assert "ecommerce" in result.output


def test_business_dashboard_not_found(temp_dbs):
    result = runner.invoke(app, ["business", "dashboard", "999"])
    assert result.exit_code == 1

# tests/test_cli_memory.py
"""Tests for CLI memory commands."""

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
    memory_db = str(tmp_path / "memory.db")
    with patch("merkaba.memory.store.MemoryStore.__init__", _make_patched_init(memory_db, "merkaba.memory.store.MemoryStore")):
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


# --- memory status ---

def test_memory_status(temp_dbs):
    result = runner.invoke(app, ["memory", "status"])
    assert result.exit_code == 0
    assert "Memory Status" in result.output


def test_memory_status_shows_categories(temp_dbs):
    result = runner.invoke(app, ["memory", "status"])
    assert result.exit_code == 0
    # Should show some category names from stats()
    assert "Count" in result.output or "Category" in result.output


# --- memory businesses ---

def test_memory_businesses_empty(temp_dbs):
    result = runner.invoke(app, ["memory", "businesses"])
    assert result.exit_code == 0
    assert "no businesses" in result.output.lower()


def test_memory_businesses_with_entries(temp_dbs):
    # Add a business via the business command with same DB patch
    from merkaba.memory.store import MemoryStore
    store = MemoryStore()
    store.add_business(name="Test Shop", type="ecommerce", autonomy_level=1)
    store.close()

    result = runner.invoke(app, ["memory", "businesses"])
    assert result.exit_code == 0
    assert "Test Shop" in result.output


# --- memory recall ---

def test_memory_recall(temp_dbs):
    with patch("merkaba.memory.retrieval.MemoryRetrieval.what_do_i_know", return_value="No relevant memories found."):
        result = runner.invoke(app, ["memory", "recall", "bittensor"])
    assert result.exit_code == 0


def test_memory_recall_with_business_filter(temp_dbs):
    with patch("merkaba.memory.retrieval.MemoryRetrieval.what_do_i_know", return_value="Filtered results") as mock_know:
        result = runner.invoke(app, ["memory", "recall", "test query", "--business", "1"])
    assert result.exit_code == 0
    mock_know.assert_called_once_with("test query", 1)


# --- memory decay ---

def test_memory_decay(temp_dbs):
    with patch("merkaba.memory.lifecycle.MemoryDecayJob.run", return_value={"decayed": 3, "archived": 1}):
        result = runner.invoke(app, ["memory", "decay"])
    assert result.exit_code == 0
    assert "3 decayed" in result.output
    assert "1 archived" in result.output


# --- memory archived ---

def test_memory_archived_empty(temp_dbs):
    result = runner.invoke(app, ["memory", "archived", "facts"])
    assert result.exit_code == 0
    assert "no archived" in result.output.lower()


def test_memory_archived_facts(temp_dbs):
    mock_items = [
        {"id": 1, "relevance_score": 0.2, "category": "research", "key": "etsy", "value": "Etsy trending data"}
    ]
    with patch("merkaba.memory.store.MemoryStore.list_archived", return_value=mock_items):
        result = runner.invoke(app, ["memory", "archived", "facts"])
    assert result.exit_code == 0
    assert "research" in result.output


def test_memory_archived_decisions(temp_dbs):
    mock_items = [
        {"id": 2, "relevance_score": 0.1, "action_type": "email_send", "decision": "Approved email blast"}
    ]
    with patch("merkaba.memory.store.MemoryStore.list_archived", return_value=mock_items):
        result = runner.invoke(app, ["memory", "archived", "decisions"])
    assert result.exit_code == 0
    assert "email_send" in result.output


def test_memory_archived_learnings(temp_dbs):
    mock_items = [
        {"id": 3, "relevance_score": 0.15, "category": "pricing", "insight": "Lower prices sell faster"}
    ]
    with patch("merkaba.memory.store.MemoryStore.list_archived", return_value=mock_items):
        result = runner.invoke(app, ["memory", "archived", "learnings"])
    assert result.exit_code == 0
    assert "pricing" in result.output


# --- memory unarchive ---

def test_memory_unarchive(temp_dbs):
    with patch("merkaba.memory.store.MemoryStore.unarchive") as mock_unarchive:
        result = runner.invoke(app, ["memory", "unarchive", "facts", "42"])
    assert result.exit_code == 0
    assert "unarchived" in result.output.lower()
    mock_unarchive.assert_called_once_with("facts", 42)


# --- memory episodes ---

def test_memory_episodes_empty(temp_dbs):
    result = runner.invoke(app, ["memory", "episodes"])
    assert result.exit_code == 0
    assert "no episodes" in result.output.lower()


def test_memory_episodes_list(temp_dbs):
    mock_episodes = [
        {
            "id": 1,
            "business_id": 1,
            "task_type": "research",
            "outcome": "success",
            "summary": "Completed etsy market research",
            "created_at": "2026-02-28T10:00:00",
        }
    ]
    with patch("merkaba.memory.store.MemoryStore.get_episodes", return_value=mock_episodes):
        result = runner.invoke(app, ["memory", "episodes"])
    assert result.exit_code == 0
    assert "research" in result.output
    assert "success" in result.output


def test_memory_episodes_detail(temp_dbs):
    mock_ep = {
        "id": 5,
        "business_id": 1,
        "task_type": "code",
        "task_id": 10,
        "outcome": "success",
        "created_at": "2026-02-28T12:00:00",
        "duration_seconds": 45,
        "summary": "Generated API endpoint",
        "outcome_details": "All tests passed",
        "key_decisions": ["Used FastAPI", "Added validation"],
        "tags": ["api", "backend"],
    }
    with patch("merkaba.memory.store.MemoryStore.get_episode", return_value=mock_ep):
        result = runner.invoke(app, ["memory", "episodes", "5"])
    assert result.exit_code == 0
    assert "Episode #5" in result.output
    assert "Generated API endpoint" in result.output
    assert "45s" in result.output
    assert "FastAPI" in result.output


def test_memory_episodes_not_found(temp_dbs):
    with patch("merkaba.memory.store.MemoryStore.get_episode", return_value=None):
        result = runner.invoke(app, ["memory", "episodes", "999"])
    assert result.exit_code == 0
    assert "not found" in result.output.lower()


# --- memory consolidate ---

def test_memory_consolidate(temp_dbs):
    with patch("merkaba.memory.lifecycle.MemoryConsolidationJob.run",
               return_value={"groups": 2, "summaries": 2, "archived": 5}):
        with patch("merkaba.llm.LLMClient"):
            result = runner.invoke(app, ["memory", "consolidate"])
    assert result.exit_code == 0
    assert "2 groups" in result.output
    assert "5 archived" in result.output

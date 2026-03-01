# tests/e2e/conftest.py
"""Shared E2E test fixtures.

Design: real SQLite databases, real CLI invocations, real plugin loading.
Only the LLM (Ollama) is mocked via the global conftest sys.modules trick.
"""

import json
import os
import sqlite3
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from merkaba.cli import app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_patched_init(db_path, class_path):
    """Create a patched __init__ that redirects a dataclass store to a temp DB.

    Reuses the proven pattern from tests/test_cli_business.py:38-55.
    """
    def patched_init(self, **kwargs):
        self.db_path = db_path
        db_dir = os.path.dirname(self.db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._create_tables()
    return patched_init


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def merkaba_home(tmp_path):
    """Create a temporary ~/.merkaba/ directory structure."""
    home = tmp_path / "merkaba_home"
    home.mkdir()
    (home / "conversations").mkdir()
    (home / "plugins").mkdir()
    (home / "businesses").mkdir()
    (home / "backups").mkdir()
    # Minimal config.json
    (home / "config.json").write_text(json.dumps({}))
    return home


@pytest.fixture()
def patched_dbs(merkaba_home):
    """Patch MemoryStore, TaskQueue, and ActionQueue to use temp SQLite paths."""
    memory_db = str(merkaba_home / "memory.db")
    tasks_db = str(merkaba_home / "tasks.db")
    actions_db = str(merkaba_home / "actions.db")

    with (
        patch(
            "merkaba.memory.store.MemoryStore.__init__",
            _make_patched_init(memory_db, "merkaba.memory.store.MemoryStore"),
        ),
        patch(
            "merkaba.orchestration.queue.TaskQueue.__init__",
            _make_patched_init(tasks_db, "merkaba.orchestration.queue.TaskQueue"),
        ),
        patch(
            "merkaba.approval.queue.ActionQueue.__init__",
            _make_patched_init(actions_db, "merkaba.approval.queue.ActionQueue"),
        ),
    ):
        yield merkaba_home


@pytest.fixture()
def cli_runner(patched_dbs):
    """Return (CliRunner, app) with patched DB environment active."""
    runner = CliRunner()
    return runner, app


@pytest.fixture()
def seeded_memory(patched_dbs):
    """Pre-populate a business + facts in the temp DB for tests that need data."""
    from merkaba.memory.store import MemoryStore

    store = MemoryStore()
    biz_id = store.add_business("Test Shop", "ecommerce", autonomy_level=2)
    store.add_fact(biz_id, "product", "material", "organic cotton")
    store.add_fact(biz_id, "product", "color", "indigo blue")
    store.add_decision(biz_id, "pricing", "Raised price 10%", "Market demand increase")
    store.add_learning("marketing", "Social media converts 3x better", confidence=85)
    store.close()
    return {"business_id": biz_id, "merkaba_home": patched_dbs}

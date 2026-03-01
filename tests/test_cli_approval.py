# tests/test_cli_approval.py
"""Tests for CLI approval commands."""

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

# Ensure ollama is mocked before importing merkaba.cli
sys.modules.setdefault("ollama", MagicMock())

from merkaba.cli import app

runner = CliRunner()


@pytest.fixture()
def temp_dbs(tmp_path):
    """Patch DB paths to use temp directory."""
    actions_db = str(tmp_path / "actions.db")
    with patch("merkaba.approval.queue.ActionQueue.__init__", _make_patched_init(actions_db, "merkaba.approval.queue.ActionQueue")):
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


# --- approval list ---

def test_approval_list_empty(temp_dbs):
    result = runner.invoke(app, ["approval", "list"])
    assert result.exit_code == 0
    assert "no actions" in result.output.lower()


def test_approval_list_with_entries(temp_dbs):
    from merkaba.approval.queue import ActionQueue
    queue = ActionQueue()
    queue.add_action(
        business_id=1,
        action_type="email_send",
        description="Send newsletter",
        params={},
        autonomy_level=2,
    )
    queue.close()

    result = runner.invoke(app, ["approval", "list"])
    assert result.exit_code == 0
    assert "email_send" in result.output
    assert "Send newsletter" in result.output


def test_approval_list_status_filter(temp_dbs):
    result = runner.invoke(app, ["approval", "list", "--status", "approved"])
    assert result.exit_code == 0
    assert "no actions" in result.output.lower()


# --- approval approve ---

def test_approval_approve(temp_dbs):
    from merkaba.approval.queue import ActionQueue
    queue = ActionQueue()
    queue.add_action(
        business_id=1,
        action_type="stripe_charge",
        description="Charge $50",
        params={},
        autonomy_level=1,
    )
    queue.close()

    with patch("merkaba.approval.graduation.GraduationChecker.check", return_value=None):
        result = runner.invoke(app, ["approval", "approve", "1"])
    assert result.exit_code == 0
    assert "approved" in result.output.lower()


def test_approval_approve_not_found(temp_dbs):
    result = runner.invoke(app, ["approval", "approve", "999"])
    assert result.exit_code == 0
    assert "cannot approve" in result.output.lower()


def test_approval_approve_with_graduation(temp_dbs):
    from merkaba.approval.queue import ActionQueue
    queue = ActionQueue()
    queue.add_action(
        business_id=1,
        action_type="email_send",
        description="Send email",
        params={},
        autonomy_level=1,
    )
    queue.close()

    graduation_suggestion = {"suggestion": "email_send has 5+ approvals — consider promoting to autonomy level 2"}
    with patch("merkaba.approval.graduation.GraduationChecker.check", return_value=graduation_suggestion):
        result = runner.invoke(app, ["approval", "approve", "1"])
    assert result.exit_code == 0
    assert "graduation" in result.output.lower()


# --- approval deny ---

def test_approval_deny(temp_dbs):
    from merkaba.approval.queue import ActionQueue
    queue = ActionQueue()
    queue.add_action(
        business_id=1,
        action_type="stripe_refund",
        description="Refund order",
        params={},
        autonomy_level=2,
    )
    queue.close()

    result = runner.invoke(app, ["approval", "deny", "1"])
    assert result.exit_code == 0
    assert "denied" in result.output.lower()


def test_approval_deny_not_found(temp_dbs):
    result = runner.invoke(app, ["approval", "deny", "999"])
    assert result.exit_code == 0
    assert "cannot deny" in result.output.lower()


# --- approval stats ---

def test_approval_stats(temp_dbs):
    result = runner.invoke(app, ["approval", "stats"])
    assert result.exit_code == 0
    assert "Approval Queue" in result.output


def test_approval_stats_with_data(temp_dbs):
    from merkaba.approval.queue import ActionQueue
    queue = ActionQueue()
    queue.add_action(business_id=1, action_type="a", description="d", params={}, autonomy_level=1)
    queue.add_action(business_id=1, action_type="b", description="d", params={}, autonomy_level=1)
    queue.close()

    result = runner.invoke(app, ["approval", "stats"])
    assert result.exit_code == 0


# --- approval graduation ---

def test_approval_graduation_no_suggestions(temp_dbs):
    with patch("merkaba.approval.graduation.GraduationChecker.check_all", return_value=[]):
        result = runner.invoke(app, ["approval", "graduation", "1"])
    assert result.exit_code == 0
    assert "no action types" in result.output.lower()


def test_approval_graduation_with_suggestions(temp_dbs):
    suggestions = [
        {"suggestion": "email_send ready for level 2"},
        {"suggestion": "stripe_charge ready for level 2"},
    ]
    with patch("merkaba.approval.graduation.GraduationChecker.check_all", return_value=suggestions):
        result = runner.invoke(app, ["approval", "graduation", "1"])
    assert result.exit_code == 0
    assert "email_send" in result.output
    assert "stripe_charge" in result.output

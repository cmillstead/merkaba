# tests/test_cli_observe.py
"""Tests for CLI observe, security, models, and backup commands."""

import json
import os
import sys
from pathlib import Path
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


# ── observe tokens ──────────────────────────────────────────────────

def test_observe_tokens_empty():
    with patch("merkaba.observability.tokens.TokenUsageStore") as MockStore:
        instance = MockStore.return_value
        instance.get_summary.return_value = []
        result = runner.invoke(app, ["observe", "tokens"])
    assert result.exit_code == 0
    assert "no token usage" in result.output.lower()


def test_observe_tokens_with_data():
    rows = [
        {"model": "qwen3:8b", "call_count": 10, "total_input": 5000,
         "total_output": 2000, "total_tokens": 7000, "total_duration_ms": 15000}
    ]
    with patch("merkaba.observability.tokens.TokenUsageStore") as MockStore:
        instance = MockStore.return_value
        instance.get_summary.return_value = rows
        result = runner.invoke(app, ["observe", "tokens"])
    assert result.exit_code == 0
    assert "qwen3:8b" in result.output
    assert "7000" in result.output


def test_observe_tokens_group_by_worker():
    rows = [
        {"worker_type": "research", "call_count": 5, "total_input": 2000,
         "total_output": 1000, "total_tokens": 3000, "total_duration_ms": 8000}
    ]
    with patch("merkaba.observability.tokens.TokenUsageStore") as MockStore:
        instance = MockStore.return_value
        instance.get_summary.return_value = rows
        result = runner.invoke(app, ["observe", "tokens", "--group-by", "worker_type"])
    assert result.exit_code == 0
    assert "research" in result.output


# ── observe audit ──────────────────────────────────────────────────

def test_observe_audit_empty():
    with patch("merkaba.observability.audit.DecisionAuditStore") as MockStore:
        instance = MockStore.return_value
        instance.get_recent.return_value = []
        result = runner.invoke(app, ["observe", "audit"])
    assert result.exit_code == 0
    assert "no decisions" in result.output.lower()


def test_observe_audit_with_data():
    decisions = [
        {"trace_id": "abc123", "decision_type": "dispatch",
         "decision": "assigned to research worker", "model": "qwen3:8b",
         "timestamp": "2026-02-28T10:00:00"}
    ]
    with patch("merkaba.observability.audit.DecisionAuditStore") as MockStore:
        instance = MockStore.return_value
        instance.get_recent.return_value = decisions
        result = runner.invoke(app, ["observe", "audit"])
    assert result.exit_code == 0
    assert "abc123" in result.output
    assert "dispatch" in result.output


def test_observe_audit_type_filter():
    with patch("merkaba.observability.audit.DecisionAuditStore") as MockStore:
        instance = MockStore.return_value
        instance.get_recent.return_value = []
        result = runner.invoke(app, ["observe", "audit", "--type", "dispatch"])
    assert result.exit_code == 0
    MockStore.return_value.get_recent.assert_called_once_with(decision_type="dispatch", limit=20)


# ── observe trace ──────────────────────────────────────────────────

def test_observe_trace_not_found():
    with patch("merkaba.observability.tokens.TokenUsageStore") as MockTokens, \
         patch("merkaba.observability.audit.DecisionAuditStore") as MockAudit:
        MockTokens.return_value.get_by_trace.return_value = []
        MockAudit.return_value.get_by_trace.return_value = []
        result = runner.invoke(app, ["observe", "trace", "nonexistent"])
    assert result.exit_code == 0
    assert "no events" in result.output.lower()


def test_observe_trace_with_data():
    decisions = [
        {"decision_type": "dispatch", "decision": "research worker",
         "alternatives": ["content", "ecommerce"], "timestamp": "2026-02-28T10:00:00"}
    ]
    tokens = [
        {"model": "qwen3:8b", "input_tokens": 500, "output_tokens": 200,
         "total_tokens": 700, "duration_ms": 1500, "timestamp": "2026-02-28T10:00:01"}
    ]
    with patch("merkaba.observability.tokens.TokenUsageStore") as MockTokens, \
         patch("merkaba.observability.audit.DecisionAuditStore") as MockAudit:
        MockTokens.return_value.get_by_trace.return_value = tokens
        MockAudit.return_value.get_by_trace.return_value = decisions
        result = runner.invoke(app, ["observe", "trace", "trace123"])
    assert result.exit_code == 0
    assert "dispatch" in result.output
    assert "qwen3:8b" in result.output


# ── security setup-2fa ─────────────────────────────────────────────

def test_security_setup_2fa_fresh():
    mock_pyotp = MagicMock()
    mock_pyotp.random_base32.return_value = "TESTBASE32SECRET"
    mock_totp = MagicMock()
    mock_totp.provisioning_uri.return_value = "otpauth://totp/merkaba?secret=TEST"
    mock_pyotp.TOTP.return_value = mock_totp

    with patch("merkaba.security.secrets.get_secret", return_value=None), \
         patch("merkaba.security.secrets.store_secret") as mock_store, \
         patch.dict("sys.modules", {"pyotp": mock_pyotp}):
        result = runner.invoke(app, ["security", "setup-2fa"])
    assert result.exit_code == 0
    assert "configured" in result.output.lower()
    assert "TESTBASE32SECRET" in result.output
    mock_store.assert_called_once_with("totp_secret", "TESTBASE32SECRET")


def test_security_setup_2fa_already_configured():
    with patch("merkaba.security.secrets.get_secret", return_value="existing_secret"):
        result = runner.invoke(app, ["security", "setup-2fa"])
    assert result.exit_code == 1
    assert "already configured" in result.output.lower()


# ── security disable-2fa ───────────────────────────────────────────

def test_security_disable_2fa_not_configured():
    with patch("merkaba.security.secrets.get_secret", return_value=None):
        result = runner.invoke(app, ["security", "disable-2fa"])
    assert result.exit_code == 0
    assert "not configured" in result.output.lower()


def test_security_disable_2fa_with_confirm():
    with patch("merkaba.security.secrets.get_secret", return_value="secret123"), \
         patch("merkaba.security.secrets.delete_secret") as mock_delete:
        result = runner.invoke(app, ["security", "disable-2fa", "--yes"])
    assert result.exit_code == 0
    assert "disabled" in result.output.lower()
    mock_delete.assert_called_once_with("totp_secret")


# ── security status ────────────────────────────────────────────────

def test_security_status_2fa_enabled(tmp_path):
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({"security": {"totp_threshold": 3}}))

    with patch("merkaba.security.secrets.get_secret", return_value="secret"), \
         patch("merkaba.cli.os.path.expanduser", return_value=str(config_file)):
        result = runner.invoke(app, ["security", "status"])
    assert result.exit_code == 0
    assert "enabled" in result.output.lower()


def test_security_status_2fa_disabled():
    with patch("merkaba.security.secrets.get_secret", return_value=None), \
         patch("merkaba.cli.os.path.expanduser", return_value="/nonexistent/config.json"):
        result = runner.invoke(app, ["security", "status"])
    assert result.exit_code == 0
    assert "disabled" in result.output.lower()


# ── models list ────────────────────────────────────────────────────

def test_models_list():
    mapping = {"research": "qwen3.5:122b", "content": "qwen3:8b"}
    with patch("merkaba.orchestration.supervisor.load_model_config", return_value=mapping), \
         patch("merkaba.orchestration.supervisor.CONFIG_PATH", "/nonexistent/config.json"):
        result = runner.invoke(app, ["models", "list"])
    assert result.exit_code == 0
    assert "research" in result.output
    assert "qwen3.5:122b" in result.output


# ── models check ───────────────────────────────────────────────────

def test_models_check_no_ollama():
    with patch("merkaba.llm.LLMClient") as MockLLM:
        MockLLM.return_value.get_available_models.return_value = []
        result = runner.invoke(app, ["models", "check"])
    assert result.exit_code == 1
    assert "could not reach" in result.output.lower() or "ollama" in result.output.lower()


def test_models_check_with_models():
    from merkaba.llm import ModelTier
    available = ["qwen3:8b", "qwen3.5:122b"]
    chains = {
        "reasoning": ModelTier(primary="qwen3.5:122b", fallbacks=["qwen3:8b"]),
    }
    with patch("merkaba.llm.LLMClient") as MockLLM, \
         patch("merkaba.llm.load_fallback_chains", return_value=chains):
        MockLLM.return_value.get_available_models.return_value = available
        result = runner.invoke(app, ["models", "check"])
    assert result.exit_code == 0
    assert "qwen3:8b" in result.output
    assert "qwen3.5:122b" in result.output


# ── models set ─────────────────────────────────────────────────────

def test_models_set(tmp_path):
    config_file = tmp_path / "config.json"
    config_file.write_text("{}")

    with patch("merkaba.orchestration.supervisor.CONFIG_PATH", str(config_file)):
        result = runner.invoke(app, ["models", "set", "research", "llama3:70b"])
    assert result.exit_code == 0
    assert "research" in result.output
    assert "llama3:70b" in result.output

    data = json.loads(config_file.read_text())
    assert data["models"]["task_types"]["research"] == "llama3:70b"


def test_models_set_merges_existing(tmp_path):
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({"models": {"task_types": {"content": "qwen3:8b"}}}))

    with patch("merkaba.orchestration.supervisor.CONFIG_PATH", str(config_file)):
        result = runner.invoke(app, ["models", "set", "research", "llama3:70b"])
    assert result.exit_code == 0

    data = json.loads(config_file.read_text())
    assert data["models"]["task_types"]["content"] == "qwen3:8b"
    assert data["models"]["task_types"]["research"] == "llama3:70b"


# ── backup run ─────────────────────────────────────────────────────

def test_backup_run(tmp_path):
    backup_dir = tmp_path / "backup_2026"
    backup_dir.mkdir()
    (backup_dir / "memory.db").write_text("fake")
    (backup_dir / "tasks.db").write_text("fake")

    with patch("merkaba.orchestration.backup.BackupManager") as MockMgr:
        MockMgr.return_value.run_backup.return_value = backup_dir
        result = runner.invoke(app, ["backup", "run"])
    assert result.exit_code == 0
    assert "backup created" in result.output.lower()
    assert "memory.db" in result.output


# ── backup list ────────────────────────────────────────────────────

def test_backup_list_empty():
    with patch("merkaba.orchestration.backup.BackupManager") as MockMgr:
        MockMgr.return_value.list_backups.return_value = []
        result = runner.invoke(app, ["backup", "list"])
    assert result.exit_code == 0
    assert "no backups" in result.output.lower()


def test_backup_list_with_entries():
    backups = [
        {"timestamp": "2026-02-28_100000", "files": ["memory.db", "tasks.db"]},
        {"timestamp": "2026-02-27_100000", "files": ["memory.db"]},
    ]
    with patch("merkaba.orchestration.backup.BackupManager") as MockMgr:
        MockMgr.return_value.list_backups.return_value = backups
        result = runner.invoke(app, ["backup", "list"])
    assert result.exit_code == 0
    assert "2026-02-28" in result.output
    assert "memory.db" in result.output


# ── backup restore ─────────────────────────────────────────────────

def test_backup_restore():
    with patch("merkaba.orchestration.backup.BackupManager") as MockMgr:
        result = runner.invoke(app, ["backup", "restore", "2026-02-28_100000", "memory.db"])
    assert result.exit_code == 0
    assert "restored" in result.output.lower()
    MockMgr.return_value.restore.assert_called_once_with("2026-02-28_100000", "memory.db")


def test_backup_restore_not_found():
    with patch("merkaba.orchestration.backup.BackupManager") as MockMgr:
        MockMgr.return_value.restore.side_effect = FileNotFoundError("Backup not found")
        result = runner.invoke(app, ["backup", "restore", "nonexistent", "memory.db"])
    assert result.exit_code == 1
    assert "not found" in result.output.lower()

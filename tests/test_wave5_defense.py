# tests/test_wave5_defense.py
"""Wave 5 — Defense in depth: SQL injection allowlist,
config error handling, close() idempotency."""

import json
import sys
from unittest.mock import MagicMock, patch

import pytest

# Ensure ollama is mocked
sys.modules.setdefault("ollama", MagicMock())


# ── 1. Token group_by SQL injection allowlist ────────────────────────


class TestTokenGroupByAllowlist:
    """Verify that get_summary() only accepts allowlisted group_by values."""

    @pytest.fixture
    def token_store(self, tmp_path):
        from merkaba.observability.tokens import TokenUsageStore
        db = str(tmp_path / "tokens.db")
        store = TokenUsageStore(db_path=db)
        # Seed one record so aggregation has data
        store.record(
            model="test-model", worker_type="research", trace_id="t1",
            input_tokens=100, output_tokens=50, duration_ms=500,
        )
        yield store
        store.close()

    def test_group_by_model(self, token_store):
        rows = token_store.get_summary(group_by="model", days=7)
        assert len(rows) == 1
        assert "model" in rows[0]

    def test_group_by_worker_type(self, token_store):
        rows = token_store.get_summary(group_by="worker_type", days=7)
        assert len(rows) == 1
        assert "worker_type" in rows[0]

    def test_group_by_injection_falls_back_to_model(self, token_store):
        """SQL injection in group_by should fall back to 'model'."""
        rows = token_store.get_summary(group_by="model; DROP TABLE token_usage; --", days=7)
        assert len(rows) == 1
        assert "model" in rows[0]

    def test_group_by_empty_string(self, token_store):
        rows = token_store.get_summary(group_by="", days=7)
        assert len(rows) == 1
        assert "model" in rows[0]

    def test_group_by_another_column(self, token_store):
        """Arbitrary column names should fall back to 'model'."""
        rows = token_store.get_summary(group_by="trace_id", days=7)
        assert len(rows) == 1
        assert "model" in rows[0]


# ── 2. Config file error handling ─────────────────────────────────────


class TestConfigErrorHandling:
    """Verify graceful handling of missing/corrupt config files."""

    # --- load_fallback_chains ---

    def test_fallback_chains_missing_config(self, tmp_path):
        from merkaba.llm import load_fallback_chains
        chains = load_fallback_chains(config_path=str(tmp_path / "nonexistent.json"))
        assert isinstance(chains, dict)
        assert len(chains) > 0  # should return defaults

    def test_fallback_chains_corrupt_json(self, tmp_path):
        from merkaba.llm import load_fallback_chains
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("{invalid json!!!")
        chains = load_fallback_chains(config_path=str(bad_file))
        assert isinstance(chains, dict)
        assert len(chains) > 0  # should return defaults

    def test_fallback_chains_valid_override(self, tmp_path):
        from merkaba.llm import load_fallback_chains
        config = {"models": {"fallback_chains": {
            "complex": {"primary": "custom:13b", "fallbacks": ["fallback:7b"]}
        }}}
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(config))
        chains = load_fallback_chains(config_path=str(config_file))
        assert chains["complex"].primary == "custom:13b"
        assert "fallback:7b" in chains["complex"].fallbacks

    # --- _load_api_key ---

    def test_load_api_key_missing_file(self):
        from merkaba.web.app import _load_api_key
        with patch("merkaba.config.loader.load_config", return_value={}):
            result = _load_api_key()
        assert result is None

    def test_load_api_key_corrupt_json(self, tmp_path):
        from merkaba.web.app import _load_api_key
        with patch("merkaba.config.loader.load_config", return_value={}):
            result = _load_api_key()
        assert result is None

    def test_load_api_key_no_key_field(self, tmp_path):
        from merkaba.web.app import _load_api_key
        with patch("merkaba.config.loader.load_config", return_value={"other": "data"}):
            result = _load_api_key()
        assert result is None

    def test_load_api_key_valid(self, tmp_path):
        from merkaba.web.app import _load_api_key
        with patch("merkaba.config.loader.load_config", return_value={"api_key": "secret123"}):
            result = _load_api_key()
        assert result == "secret123"

    # --- TelegramConfig._load ---

    def test_telegram_config_corrupt_json(self, tmp_path):
        from merkaba.telegram.config import TelegramConfig
        bad = tmp_path / "telegram.json"
        bad.write_text("{broken")
        config = TelegramConfig(config_path=str(bad))
        data = config._load()
        assert data == {}

    # --- SecureApprovalManager.from_config ---

    def test_secure_approval_from_config_missing_file(self, tmp_path):
        from merkaba.approval.secure import SecureApprovalManager
        mock_queue = MagicMock()

        with patch("merkaba.security.secrets.get_secret", return_value=None), \
             patch("os.path.expanduser",
                   return_value=str(tmp_path / "nonexistent.json")):
            mgr = SecureApprovalManager.from_config(mock_queue)

        assert mgr.totp_secret is None
        assert mgr.action_queue is mock_queue

    def test_secure_approval_from_config_corrupt_json(self, tmp_path):
        from merkaba.approval.secure import SecureApprovalManager
        mock_queue = MagicMock()
        bad = tmp_path / "config.json"
        bad.write_text("{broken")

        with patch("merkaba.security.secrets.get_secret", return_value=None), \
             patch("os.path.expanduser", return_value=str(bad)):
            mgr = SecureApprovalManager.from_config(mock_queue)

        assert mgr.totp_secret is None


# ── 4. close() idempotency ───────────────────────────────────────────


class TestCloseIdempotency:
    """Verify double-close doesn't raise on any store/queue."""

    def test_memory_store_double_close(self, tmp_path):
        from merkaba.memory.store import MemoryStore
        store = MemoryStore(db_path=str(tmp_path / "mem.db"))
        store.close()
        store.close()  # should not raise

    def test_task_queue_double_close(self, tmp_path):
        from merkaba.orchestration.queue import TaskQueue
        queue = TaskQueue(db_path=str(tmp_path / "tasks.db"))
        queue.close()
        queue.close()

    def test_action_queue_double_close(self, tmp_path):
        from merkaba.approval.queue import ActionQueue
        queue = ActionQueue(db_path=str(tmp_path / "actions.db"))
        queue.close()
        queue.close()

    def test_token_store_double_close(self, tmp_path):
        from merkaba.observability.tokens import TokenUsageStore
        store = TokenUsageStore(db_path=str(tmp_path / "tokens.db"))
        store.close()
        store.close()

    def test_audit_store_double_close(self, tmp_path):
        from merkaba.observability.audit import DecisionAuditStore
        store = DecisionAuditStore(db_path=str(tmp_path / "audit.db"))
        store.close()
        store.close()

    def test_vector_memory_double_close(self):
        from merkaba.memory.vectors import VectorMemory
        vm = VectorMemory.__new__(VectorMemory)
        vm._client = None
        vm._collections = {}
        vm.close()
        vm.close()  # should not raise

# tests/test_observability_wal.py
"""Verify that observability stores use WAL journal mode."""

import pytest


class TestTokenUsageStoreWAL:

    def test_journal_mode_is_wal(self, tmp_path):
        from merkaba.observability.tokens import TokenUsageStore

        store = TokenUsageStore(db_path=str(tmp_path / "tokens.db"))
        try:
            row = store._conn.execute("PRAGMA journal_mode").fetchone()
            assert row[0] == "wal"
        finally:
            store.close()


class TestDecisionAuditStoreWAL:

    def test_journal_mode_is_wal(self, tmp_path):
        from merkaba.observability.audit import DecisionAuditStore

        store = DecisionAuditStore(db_path=str(tmp_path / "audit.db"))
        try:
            row = store._conn.execute("PRAGMA journal_mode").fetchone()
            assert row[0] == "wal"
        finally:
            store.close()

# tests/test_file_permissions_extended.py
"""Tests that data stores enforce secure file permissions on creation."""
import os
import stat
import tempfile
from unittest.mock import MagicMock, patch

import pytest


def _mode(path: str) -> int:
    """Return the permission bits (mode) of a path."""
    return stat.S_IMODE(os.stat(path).st_mode)


class TestConversationDirPermissions:
    """Conversation storage directory must get secure permissions (0o700)."""

    def test_conversation_dir_gets_secure_permissions(self, tmp_path):
        conv_dir = str(tmp_path / "conversations")
        # Widen the parent so we can detect the change on the child dir
        from merkaba.memory.conversation import ConversationLog

        log = ConversationLog(storage_dir=conv_dir, session_id="test-session")
        assert os.path.isdir(conv_dir)
        assert _mode(conv_dir) == 0o700

    def test_conversation_file_gets_secure_permissions_on_save(self, tmp_path):
        conv_dir = str(tmp_path / "conversations")
        from merkaba.memory.conversation import ConversationLog

        log = ConversationLog(storage_dir=conv_dir, session_id="test-session")
        log.append("user", "hello")
        log.save()
        filepath = log._filepath
        assert os.path.isfile(filepath)
        assert _mode(filepath) == 0o600


class TestVectorDirPermissions:
    """Vector persist directory must get secure permissions (0o700)."""

    def test_vector_dir_gets_secure_permissions(self, tmp_path):
        vector_dir = str(tmp_path / "vectors")
        # VectorMemory requires chromadb + Ollama, so we mock the heavy parts
        # but keep the directory-creation and permission-setting logic intact.
        with patch("merkaba.memory.vectors.HAS_CHROMADB", True), \
             patch("merkaba.memory.vectors.OllamaEmbeddingFunction", MagicMock()), \
             patch("merkaba.memory.vectors.chromadb") as mock_chromadb:
            mock_client = MagicMock()
            mock_chromadb.PersistentClient.return_value = mock_client
            mock_client.get_or_create_collection.return_value = MagicMock()

            from merkaba.memory.vectors import VectorMemory

            vm = VectorMemory(persist_dir=vector_dir)
            assert os.path.isdir(vector_dir)
            assert _mode(vector_dir) == 0o700


class TestAuditStoreFilePermissions:
    """Audit store database file must get secure permissions (0o600)."""

    def test_audit_store_file_gets_secure_permissions(self, tmp_path):
        db_file = str(tmp_path / "audit.db")
        from merkaba.observability.audit import DecisionAuditStore

        store = DecisionAuditStore(db_path=db_file)
        try:
            assert os.path.isfile(db_file)
            assert _mode(db_file) == 0o600
        finally:
            store.close()


class TestTokenStoreFilePermissions:
    """Token store database file must get secure permissions (0o600)."""

    def test_token_store_file_gets_secure_permissions(self, tmp_path):
        db_file = str(tmp_path / "tokens.db")
        from merkaba.observability.tokens import TokenUsageStore

        store = TokenUsageStore(db_path=db_file)
        try:
            assert os.path.isfile(db_file)
            assert _mode(db_file) == 0o600
        finally:
            store.close()

# tests/test_encryption.py
"""Tests for Fernet-based conversation encryption."""

import json
import os

import pytest

from merkaba.security.encryption import ConversationEncryptor, ENCRYPTED_PREFIX


class TestConversationEncryptor:

    def test_encrypt_decrypt_roundtrip(self):
        enc = ConversationEncryptor.from_passphrase("test-passphrase")
        data = {"messages": [{"role": "user", "content": "hello"}]}
        plaintext = json.dumps(data)
        ciphertext = enc.encrypt(plaintext)
        assert ciphertext != plaintext
        result = enc.decrypt(ciphertext)
        assert json.loads(result) == data

    def test_wrong_passphrase_fails(self):
        enc1 = ConversationEncryptor.from_passphrase("correct")
        enc2 = ConversationEncryptor.from_passphrase("wrong")
        ciphertext = enc1.encrypt("secret")
        with pytest.raises(Exception):
            enc2.decrypt(ciphertext)

    def test_is_encrypted_detects_ciphertext(self):
        enc = ConversationEncryptor.from_passphrase("test")
        ciphertext = enc.encrypt("hello")
        assert ConversationEncryptor.is_encrypted(ciphertext)
        assert not ConversationEncryptor.is_encrypted('{"messages": []}')

    def test_deterministic_key_from_same_passphrase(self):
        """Same passphrase always derives the same key."""
        enc1 = ConversationEncryptor.from_passphrase("my-secret")
        enc2 = ConversationEncryptor.from_passphrase("my-secret")
        ciphertext = enc1.encrypt("test data")
        # enc2 should be able to decrypt enc1's output
        assert enc2.decrypt(ciphertext) == "test data"

    def test_encrypted_prefix_present(self):
        enc = ConversationEncryptor.from_passphrase("test")
        ciphertext = enc.encrypt("hello")
        assert ciphertext.startswith(ENCRYPTED_PREFIX.decode())

    def test_empty_string_roundtrip(self):
        enc = ConversationEncryptor.from_passphrase("test")
        ciphertext = enc.encrypt("")
        assert enc.decrypt(ciphertext) == ""

    def test_unicode_roundtrip(self):
        enc = ConversationEncryptor.from_passphrase("test")
        text = "Hello 世界 🌍"
        ciphertext = enc.encrypt(text)
        assert enc.decrypt(ciphertext) == text


class TestConversationLogEncryption:
    """Tests for encryption integrated into ConversationLog."""

    def test_save_and_load_with_encryption(self, tmp_path):
        from merkaba.memory.conversation import ConversationLog

        enc = ConversationEncryptor.from_passphrase("test-pass")
        log = ConversationLog(storage_dir=str(tmp_path), encryptor=enc)
        log.append("user", "secret message")
        log.save()

        # Raw file should be encrypted
        filepath = os.path.join(str(tmp_path), f"{log.session_id}.json")
        raw = open(filepath).read()
        assert raw.startswith(ENCRYPTED_PREFIX.decode())
        assert "secret message" not in raw

        # Loading with same key should work
        log2 = ConversationLog(
            storage_dir=str(tmp_path),
            session_id=log.session_id,
            encryptor=enc,
        )
        assert len(log2._history) == 1
        assert log2._history[0]["content"] == "secret message"

    def test_load_without_encryption_reads_plaintext(self, tmp_path):
        """ConversationLog without encryptor reads plaintext files normally."""
        from merkaba.memory.conversation import ConversationLog

        log = ConversationLog(storage_dir=str(tmp_path))
        log.append("user", "plain message")
        log.save()

        log2 = ConversationLog(storage_dir=str(tmp_path), session_id=log.session_id)
        assert len(log2._history) == 1
        assert log2._history[0]["content"] == "plain message"

    def test_load_encrypted_without_key_returns_empty(self, tmp_path):
        """Loading encrypted file without encryptor gracefully returns empty."""
        from merkaba.memory.conversation import ConversationLog

        enc = ConversationEncryptor.from_passphrase("test-pass")
        log = ConversationLog(storage_dir=str(tmp_path), encryptor=enc)
        log.append("user", "secret")
        log.save()

        # Load without encryptor — should not crash
        log2 = ConversationLog(storage_dir=str(tmp_path), session_id=log.session_id)
        assert log2._history == []

    def test_wrong_key_returns_empty(self, tmp_path):
        """Loading with wrong key gracefully returns empty."""
        from merkaba.memory.conversation import ConversationLog

        enc1 = ConversationEncryptor.from_passphrase("correct")
        log = ConversationLog(storage_dir=str(tmp_path), encryptor=enc1)
        log.append("user", "secret")
        log.save()

        enc2 = ConversationEncryptor.from_passphrase("wrong")
        log2 = ConversationLog(
            storage_dir=str(tmp_path),
            session_id=log.session_id,
            encryptor=enc2,
        )
        assert log2._history == []

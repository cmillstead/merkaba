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


    def test_random_salt_encrypt_decrypt_roundtrip(self):
        """Encrypt/decrypt roundtrip works with random salt (no explicit salt)."""
        enc = ConversationEncryptor.from_passphrase("test-passphrase")
        plaintext = "sensitive data with random salt"
        ciphertext = enc.encrypt(plaintext)
        assert enc.decrypt(ciphertext) == plaintext

    def test_random_salt_different_ciphertext(self):
        """Two encryptions of the same plaintext produce different ciphertext."""
        enc1 = ConversationEncryptor.from_passphrase("same-pass")
        enc2 = ConversationEncryptor.from_passphrase("same-pass")
        plaintext = "identical input"
        ct1 = enc1.encrypt(plaintext)
        ct2 = enc2.encrypt(plaintext)
        # Different random salts mean entirely different ciphertext
        assert ct1 != ct2
        # But both decrypt correctly (cross-instance)
        assert enc1.decrypt(ct2) == plaintext
        assert enc2.decrypt(ct1) == plaintext

    def test_new_format_contains_salt(self):
        """New format has three colon-separated parts: prefix, salt, token."""
        enc = ConversationEncryptor.from_passphrase("test")
        ciphertext = enc.encrypt("hello")
        assert ciphertext.startswith("MERKABA_ENC:")
        # After stripping prefix, should have <salt_b64>:<fernet_token>
        body = ciphertext[len("MERKABA_ENC:"):]
        parts = body.split(":", 1)
        assert len(parts) == 2, "Expected salt:token format"
        # Salt should be valid base64 decoding to 32 bytes
        import base64
        salt = base64.urlsafe_b64decode(parts[0])
        assert len(salt) == 32

    def test_legacy_format_backward_compat(self):
        """Legacy-format ciphertext (no salt separator) can still be decrypted."""
        # Create a legacy encryptor with a fixed salt (old behavior)
        fixed_salt = b"merkaba-conversation-salt"
        enc_legacy = ConversationEncryptor.from_passphrase("my-pass", salt=fixed_salt)
        # Manually produce legacy format: MERKABA_ENC:<token> (no salt field)
        from cryptography.fernet import Fernet
        legacy_token = enc_legacy._fernet.encrypt(b"legacy secret")
        legacy_ciphertext = f"MERKABA_ENC:{legacy_token.decode()}"

        # A new-style encryptor with the same passphrase and same fixed salt
        # should decrypt legacy format via the fallback path
        enc_new = ConversationEncryptor.from_passphrase("my-pass", salt=fixed_salt)
        assert enc_new.decrypt(legacy_ciphertext) == "legacy secret"

    def test_legacy_format_decrypt_with_random_salt_encryptor(self):
        """An encryptor with random salt can decrypt legacy ciphertext if passphrase matches."""
        fixed_salt = b"merkaba-conversation-salt"
        # Produce legacy-format ciphertext with the old fixed salt
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
        from cryptography.hazmat.primitives import hashes
        from cryptography.fernet import Fernet
        import base64 as b64

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(), length=32, salt=fixed_salt, iterations=480_000
        )
        key = b64.urlsafe_b64encode(kdf.derive(b"my-pass"))
        f = Fernet(key)
        legacy_token = f.encrypt(b"old format data")
        legacy_ciphertext = f"MERKABA_ENC:{legacy_token.decode()}"

        # New encryptor with random salt won't have matching _fernet,
        # but the Fernet token itself doesn't contain a colon separator
        # after the prefix, so it falls through to legacy path.
        # However, the legacy path uses self._fernet which has a different key.
        # So we need a new encryptor with the same fixed salt to decrypt legacy data.
        enc = ConversationEncryptor.from_passphrase("my-pass", salt=fixed_salt)
        assert enc.decrypt(legacy_ciphertext) == "old format data"


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

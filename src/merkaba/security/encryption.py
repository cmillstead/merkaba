# src/merkaba/security/encryption.py
"""Fernet-based conversation encryption at rest."""

import base64
import logging
import os

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

ENCRYPTED_PREFIX = b"MERKABA_ENC:"

logger = logging.getLogger(__name__)


class ConversationEncryptor:
    """Encrypts and decrypts conversation data using Fernet symmetric encryption."""

    def __init__(self, key: bytes, *, salt: bytes | None = None, passphrase: str | None = None):
        self._fernet = Fernet(key)
        self._salt = salt
        self._passphrase = passphrase

    @classmethod
    def from_passphrase(cls, passphrase: str, salt: bytes | None = None) -> "ConversationEncryptor":
        """Derive a Fernet key from a passphrase using PBKDF2.

        When salt is None, a random 32-byte salt is generated. The salt is
        stored in the instance and embedded in the ciphertext output so that
        decryption can re-derive the same key.
        """
        if salt is None:
            salt = os.urandom(32)
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=480_000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(passphrase.encode()))
        return cls(key, salt=salt, passphrase=passphrase)

    @classmethod
    def from_keychain(cls) -> "ConversationEncryptor | None":
        """Load encryption key from OS keychain. Returns None if not configured."""
        try:
            from merkaba.security.secrets import get_secret
            key_b64 = get_secret("conversation_encryption_key")
            if key_b64:
                return cls(key_b64.encode())
        except Exception as e:
            logger.warning("Failed to load encryption key from keychain: %s", e)
        return None

    def encrypt(self, plaintext: str) -> str:
        """Encrypt plaintext, returning prefixed ciphertext string.

        Output format: ``MERKABA_ENC:<base64_salt>:<ciphertext>`` when a salt
        is available (passphrase-derived keys).  For keychain-loaded keys
        (no salt), the legacy format ``MERKABA_ENC:<ciphertext>`` is used.
        """
        token = self._fernet.encrypt(plaintext.encode())
        if self._salt is not None:
            salt_b64 = base64.urlsafe_b64encode(self._salt)
            return (ENCRYPTED_PREFIX + salt_b64 + b":" + token).decode()
        return (ENCRYPTED_PREFIX + token).decode()

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt ciphertext, handling both new and legacy formats.

        New format: ``MERKABA_ENC:<base64_salt>:<ciphertext>``
        Legacy format: ``MERKABA_ENC:<ciphertext>``

        For the new format, the embedded salt is used to re-derive the key
        from the stored passphrase before decrypting. For legacy format,
        the instance's own Fernet key is used directly.
        """
        raw = ciphertext.encode()
        if raw.startswith(ENCRYPTED_PREFIX):
            raw = raw[len(ENCRYPTED_PREFIX):]

        # Try new format: <base64_salt>:<fernet_token>
        # Fernet tokens always start with 'gAAAAA' (base64 of version byte + timestamp).
        # If there's a colon and the part after it looks like a Fernet token, parse as new format.
        colon_idx = raw.find(b":")
        if colon_idx > 0 and self._passphrase is not None:
            maybe_salt_b64 = raw[:colon_idx]
            maybe_token = raw[colon_idx + 1:]
            try:
                salt = base64.urlsafe_b64decode(maybe_salt_b64)
                if len(salt) == 32:
                    # Re-derive key from embedded salt
                    kdf = PBKDF2HMAC(
                        algorithm=hashes.SHA256(),
                        length=32,
                        salt=salt,
                        iterations=480_000,
                    )
                    key = base64.urlsafe_b64encode(kdf.derive(self._passphrase.encode()))
                    f = Fernet(key)
                    return f.decrypt(maybe_token).decode()
            except Exception as e:
                logger.warning("Failed to decrypt with embedded salt, falling back to legacy: %s", e)

        # Legacy format or keychain-based: use instance Fernet directly
        return self._fernet.decrypt(raw).decode()

    @staticmethod
    def is_encrypted(data: str) -> bool:
        """Check if data has the MERKABA_ENC: encryption prefix."""
        return data.startswith(ENCRYPTED_PREFIX.decode())

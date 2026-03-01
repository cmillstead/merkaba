# src/friday/security/encryption.py
"""Fernet-based conversation encryption at rest."""

import base64

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

ENCRYPTED_PREFIX = b"FRIDAY_ENC:"


class ConversationEncryptor:
    """Encrypts and decrypts conversation data using Fernet symmetric encryption."""

    def __init__(self, key: bytes):
        self._fernet = Fernet(key)

    @classmethod
    def from_passphrase(cls, passphrase: str, salt: bytes | None = None) -> "ConversationEncryptor":
        """Derive a Fernet key from a passphrase using PBKDF2."""
        if salt is None:
            salt = b"friday-conversation-salt"
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=480_000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(passphrase.encode()))
        return cls(key)

    @classmethod
    def from_keychain(cls) -> "ConversationEncryptor | None":
        """Load encryption key from OS keychain. Returns None if not configured."""
        try:
            from friday.security.secrets import get_secret
            key_b64 = get_secret("conversation_encryption_key")
            if key_b64:
                return cls(key_b64.encode())
        except Exception:
            pass
        return None

    def encrypt(self, plaintext: str) -> str:
        """Encrypt plaintext, returning prefixed ciphertext string."""
        token = self._fernet.encrypt(plaintext.encode())
        return (ENCRYPTED_PREFIX + token).decode()

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt ciphertext, stripping the prefix if present."""
        raw = ciphertext.encode()
        if raw.startswith(ENCRYPTED_PREFIX):
            raw = raw[len(ENCRYPTED_PREFIX):]
        return self._fernet.decrypt(raw).decode()

    @staticmethod
    def is_encrypted(data: str) -> bool:
        """Check if data has the FRIDAY_ENC: encryption prefix."""
        return data.startswith(ENCRYPTED_PREFIX.decode())

# src/friday/security/secrets.py
"""Secure secrets management using OS keychain."""

import keyring
import keyring.errors

SERVICE_NAME = "friday-ai"


def store_secret(key: str, value: str) -> None:
    """Store a secret in the OS keychain.

    Args:
        key: The identifier for the secret.
        value: The secret value to store.
    """
    keyring.set_password(SERVICE_NAME, key, value)


def get_secret(key: str) -> str | None:
    """Retrieve a secret from the OS keychain.

    Args:
        key: The identifier for the secret.

    Returns:
        The secret value, or None if not found.
    """
    return keyring.get_password(SERVICE_NAME, key)


def delete_secret(key: str) -> None:
    """Delete a secret from the OS keychain.

    Args:
        key: The identifier for the secret to delete.

    Note:
        Does not raise an error if the secret does not exist.
    """
    try:
        keyring.delete_password(SERVICE_NAME, key)
    except keyring.errors.PasswordDeleteError:
        # Secret doesn't exist, ignore
        pass

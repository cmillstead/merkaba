# tests/test_secrets.py
"""Tests for secure secrets management."""

import pytest

# Check if required dependencies are available
try:
    import keyring.errors
    from merkaba.security.secrets import (
        SERVICE_NAME,
        store_secret,
        get_secret,
        delete_secret,
    )
    HAS_DEPENDENCIES = True
except ImportError as e:
    HAS_DEPENDENCIES = False
    IMPORT_ERROR = str(e)
    keyring = None
    SERVICE_NAME = None
    store_secret = None
    get_secret = None
    delete_secret = None

pytestmark = pytest.mark.skipif(
    not HAS_DEPENDENCIES,
    reason=f"Missing required dependencies: {IMPORT_ERROR if not HAS_DEPENDENCIES else ''}"
)


class TestStoreSecret:
    """Tests for store_secret function."""

    def test_store_secret_calls_keyring(self, mocker):
        """Test that store_secret correctly calls keyring.set_password."""
        mock_set_password = mocker.patch("merkaba.security.secrets.keyring.set_password")

        store_secret("api_key", "secret_value_123")

        mock_set_password.assert_called_once_with(
            SERVICE_NAME, "api_key", "secret_value_123"
        )


class TestGetSecret:
    """Tests for get_secret function."""

    def test_get_secret_returns_value(self, mocker):
        """Test that get_secret returns the stored value."""
        mock_get_password = mocker.patch(
            "merkaba.security.secrets.keyring.get_password",
            return_value="my_secret_value",
        )

        result = get_secret("api_key")

        assert result == "my_secret_value"
        mock_get_password.assert_called_once_with(SERVICE_NAME, "api_key")

    def test_get_secret_returns_none_for_nonexistent(self, mocker):
        """Test that get_secret returns None for non-existent secrets."""
        mocker.patch(
            "merkaba.security.secrets.keyring.get_password",
            return_value=None,
        )

        result = get_secret("nonexistent_key")

        assert result is None


class TestDeleteSecret:
    """Tests for delete_secret function."""

    def test_delete_secret_calls_keyring(self, mocker):
        """Test that delete_secret correctly calls keyring.delete_password."""
        mock_delete_password = mocker.patch(
            "merkaba.security.secrets.keyring.delete_password"
        )

        delete_secret("api_key")

        mock_delete_password.assert_called_once_with(SERVICE_NAME, "api_key")

    def test_delete_nonexistent_secret_does_not_error(self, mocker):
        """Test that deleting a non-existent secret doesn't raise an error."""
        mock_delete_password = mocker.patch(
            "merkaba.security.secrets.keyring.delete_password",
            side_effect=keyring.errors.PasswordDeleteError("Secret not found"),
        )

        # Should not raise any exception
        delete_secret("nonexistent_key")

        mock_delete_password.assert_called_once_with(SERVICE_NAME, "nonexistent_key")


class TestSecretsIntegration:
    """Integration-style tests for secrets workflow."""

    def test_store_and_retrieve_secret(self, mocker):
        """Test storing and retrieving a secret."""
        stored_secrets = {}

        def mock_set(service, key, value):
            stored_secrets[(service, key)] = value

        def mock_get(service, key):
            return stored_secrets.get((service, key))

        mocker.patch(
            "merkaba.security.secrets.keyring.set_password",
            side_effect=mock_set,
        )
        mocker.patch(
            "merkaba.security.secrets.keyring.get_password",
            side_effect=mock_get,
        )

        # Store a secret
        store_secret("test_token", "super_secret_123")

        # Retrieve it
        result = get_secret("test_token")

        assert result == "super_secret_123"

    def test_delete_existing_secret(self, mocker):
        """Test deleting an existing secret."""
        stored_secrets = {(SERVICE_NAME, "to_delete"): "value"}

        def mock_delete(service, key):
            if (service, key) not in stored_secrets:
                raise keyring.errors.PasswordDeleteError("Not found")
            del stored_secrets[(service, key)]

        def mock_get(service, key):
            return stored_secrets.get((service, key))

        mocker.patch(
            "merkaba.security.secrets.keyring.delete_password",
            side_effect=mock_delete,
        )
        mocker.patch(
            "merkaba.security.secrets.keyring.get_password",
            side_effect=mock_get,
        )

        # Delete the secret
        delete_secret("to_delete")

        # Verify it's gone
        result = get_secret("to_delete")
        assert result is None


class TestStoreSecretErrorHandling:
    """Tests for store_secret keyring error propagation."""

    def test_store_secret_propagates_runtime_error(self, mocker):
        """store_secret does not catch RuntimeError from keyring — it propagates."""
        mocker.patch(
            "merkaba.security.secrets.keyring.set_password",
            side_effect=RuntimeError("keychain locked"),
        )

        with pytest.raises(RuntimeError, match="keychain locked"):
            store_secret("api_key", "value")

    def test_store_secret_propagates_keyring_error(self, mocker):
        """store_secret does not catch KeyringError — it propagates."""
        mocker.patch(
            "merkaba.security.secrets.keyring.set_password",
            side_effect=keyring.errors.KeyringError("backend unavailable"),
        )

        with pytest.raises(keyring.errors.KeyringError, match="backend unavailable"):
            store_secret("api_key", "value")

    def test_store_secret_with_empty_value(self, mocker):
        """store_secret with empty string value still calls keyring correctly."""
        mock_set = mocker.patch("merkaba.security.secrets.keyring.set_password")

        store_secret("empty_key", "")

        mock_set.assert_called_once_with(SERVICE_NAME, "empty_key", "")


class TestGetSecretErrorHandling:
    """Tests for get_secret keyring error propagation."""

    def test_get_secret_propagates_runtime_error(self, mocker):
        """get_secret does not catch RuntimeError from keyring — it propagates."""
        mocker.patch(
            "merkaba.security.secrets.keyring.get_password",
            side_effect=RuntimeError("keychain locked"),
        )

        with pytest.raises(RuntimeError, match="keychain locked"):
            get_secret("api_key")

    def test_get_secret_propagates_keyring_error(self, mocker):
        """get_secret does not catch KeyringError — it propagates."""
        mocker.patch(
            "merkaba.security.secrets.keyring.get_password",
            side_effect=keyring.errors.KeyringError("backend unavailable"),
        )

        with pytest.raises(keyring.errors.KeyringError, match="backend unavailable"):
            get_secret("api_key")

    def test_get_secret_with_special_chars_in_key(self, mocker):
        """get_secret with special characters in key works correctly."""
        mock_get = mocker.patch(
            "merkaba.security.secrets.keyring.get_password",
            return_value="found_it",
        )

        result = get_secret("my/key@with#special!chars")

        assert result == "found_it"
        mock_get.assert_called_once_with(SERVICE_NAME, "my/key@with#special!chars")


class TestDeleteSecretErrorHandling:
    """Tests for delete_secret — only PasswordDeleteError is caught."""

    def test_delete_secret_propagates_runtime_error(self, mocker):
        """delete_secret does NOT catch RuntimeError — only PasswordDeleteError."""
        mocker.patch(
            "merkaba.security.secrets.keyring.delete_password",
            side_effect=RuntimeError("keychain locked"),
        )

        with pytest.raises(RuntimeError, match="keychain locked"):
            delete_secret("api_key")

    def test_delete_secret_propagates_keyring_error(self, mocker):
        """delete_secret does NOT catch KeyringError — only PasswordDeleteError."""
        mocker.patch(
            "merkaba.security.secrets.keyring.delete_password",
            side_effect=keyring.errors.KeyringError("backend unavailable"),
        )

        with pytest.raises(keyring.errors.KeyringError, match="backend unavailable"):
            delete_secret("api_key")

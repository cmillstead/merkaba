# tests/test_credentials_manager.py
import pytest

try:
    import keyring.errors
    from merkaba.integrations.credentials import CredentialManager
    HAS_DEPENDENCIES = True
except ImportError as e:
    HAS_DEPENDENCIES = False
    IMPORT_ERROR = str(e)

pytestmark = pytest.mark.skipif(
    not HAS_DEPENDENCIES,
    reason=f"Missing required dependencies: {IMPORT_ERROR if not HAS_DEPENDENCIES else ''}"
)


@pytest.fixture
def creds(mocker):
    stored = {}

    def mock_set(service, key, value):
        stored[(service, key)] = value

    def mock_get(service, key):
        return stored.get((service, key))

    def mock_delete(service, key):
        if (service, key) not in stored:
            raise keyring.errors.PasswordDeleteError("Not found")
        del stored[(service, key)]

    mocker.patch("merkaba.security.secrets.keyring.set_password", side_effect=mock_set)
    mocker.patch("merkaba.security.secrets.keyring.get_password", side_effect=mock_get)
    mocker.patch("merkaba.security.secrets.keyring.delete_password", side_effect=mock_delete)

    return CredentialManager()


class TestCredentialManager:

    def test_store_and_get(self, creds):
        creds.store("stripe", "api_key", "sk_test_123")
        assert creds.get("stripe", "api_key") == "sk_test_123"

    def test_get_missing_returns_none(self, creds):
        assert creds.get("stripe", "nonexistent") is None

    def test_delete(self, creds):
        creds.store("email", "password", "secret")
        creds.delete("email", "password")
        assert creds.get("email", "password") is None

    def test_delete_missing_does_not_error(self, creds):
        creds.delete("email", "nonexistent")

    def test_namespacing(self, creds):
        creds.store("stripe", "api_key", "stripe_key")
        creds.store("email", "api_key", "email_key")
        assert creds.get("stripe", "api_key") == "stripe_key"
        assert creds.get("email", "api_key") == "email_key"

    def test_has_required_all_present(self, creds):
        creds.store("stripe", "api_key", "sk_test")
        ok, missing = creds.has_required("stripe", ["api_key"])
        assert ok is True
        assert missing == []

    def test_has_required_some_missing(self, creds):
        creds.store("email", "smtp_host", "smtp.gmail.com")
        ok, missing = creds.has_required("email", ["smtp_host", "smtp_password"])
        assert ok is False
        assert missing == ["smtp_password"]

    def test_has_required_all_missing(self, creds):
        ok, missing = creds.has_required("stripe", ["api_key", "webhook_secret"])
        assert ok is False
        assert set(missing) == {"api_key", "webhook_secret"}

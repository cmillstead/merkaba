# tests/test_email_adapter.py
import sys
from email.message import EmailMessage
from unittest.mock import MagicMock, patch

import pytest

try:
    import keyring.errors
    HAS_DEPS = True
except ImportError:
    HAS_DEPS = False

pytestmark = pytest.mark.skipif(not HAS_DEPS, reason="Missing keyring")

from merkaba.integrations.email_adapter import EmailAdapter
from merkaba.integrations.base import ADAPTER_REGISTRY


def test_email_adapter_registered():
    assert "email" in ADAPTER_REGISTRY


@pytest.fixture
def email_adapter(mocker):
    stored = {
        ("merkaba-ai", "integration:email:smtp_host"): "smtp.test.com",
        ("merkaba-ai", "integration:email:smtp_port"): "587",
        ("merkaba-ai", "integration:email:smtp_user"): "user@test.com",
        ("merkaba-ai", "integration:email:smtp_password"): "pass123",
        ("merkaba-ai", "integration:email:imap_host"): "imap.test.com",
        ("merkaba-ai", "integration:email:imap_user"): "user@test.com",
        ("merkaba-ai", "integration:email:imap_password"): "pass123",
    }
    mocker.patch(
        "merkaba.security.secrets.keyring.get_password",
        side_effect=lambda svc, key: stored.get((svc, key)),
    )
    return EmailAdapter(name="email")


def test_connect_loads_credentials(email_adapter):
    result = email_adapter.connect()
    assert result is True
    assert email_adapter.is_connected is True


def test_connect_fails_missing_credentials(mocker):
    mocker.patch("merkaba.security.secrets.keyring.get_password", return_value=None)
    adapter = EmailAdapter(name="email")
    result = adapter.connect()
    assert result is False
    assert adapter.is_connected is False


def test_execute_send(email_adapter, mocker):
    email_adapter.connect()
    mock_smtp = MagicMock()
    mocker.patch("smtplib.SMTP", return_value=mock_smtp)
    mock_smtp.__enter__ = MagicMock(return_value=mock_smtp)
    mock_smtp.__exit__ = MagicMock(return_value=False)

    result = email_adapter.execute("send", {
        "to": "recipient@test.com",
        "subject": "Test",
        "body": "Hello",
    })

    assert result["ok"] is True
    mock_smtp.send_message.assert_called_once()


def test_execute_send_missing_params(email_adapter):
    email_adapter.connect()
    result = email_adapter.execute("send", {"to": "x@x.com"})
    assert result["ok"] is False
    assert "error" in result


def test_execute_read_inbox(email_adapter, mocker):
    email_adapter.connect()

    msg = EmailMessage()
    msg["From"] = "sender@test.com"
    msg["Subject"] = "Hello"
    msg.set_content("Test body")
    raw_bytes = msg.as_bytes()

    mock_imap = MagicMock()
    mocker.patch("imaplib.IMAP4_SSL", return_value=mock_imap)
    mock_imap.search.return_value = ("OK", [b"1"])
    mock_imap.fetch.return_value = ("OK", [(b"1", raw_bytes)])

    result = email_adapter.execute("read_inbox", {"limit": 1})

    assert result["ok"] is True
    assert len(result["emails"]) == 1
    assert result["emails"][0]["from"] == "sender@test.com"
    assert result["emails"][0]["subject"] == "Hello"


def test_execute_parse_email(email_adapter, mocker):
    email_adapter.connect()

    mock_llm = MagicMock()
    mock_llm.chat.return_value = MagicMock(
        content='{"intent": "order_inquiry", "order_id": "12345", "customer": "John"}'
    )
    mocker.patch("merkaba.integrations.email_adapter.EmailAdapter._get_llm", return_value=mock_llm)

    result = email_adapter.execute("parse_email", {
        "from": "customer@test.com",
        "subject": "Order #12345",
        "body": "Where is my order #12345? - John",
    })

    assert result["ok"] is True
    assert result["parsed"]["intent"] == "order_inquiry"


def test_execute_unknown_action(email_adapter):
    email_adapter.connect()
    result = email_adapter.execute("unknown_action")
    assert result["ok"] is False
    assert "Unknown action" in result["error"]


def test_health_check_connected(email_adapter):
    email_adapter.connect()
    result = email_adapter.health_check()
    assert result["ok"] is True


def test_health_check_not_connected():
    adapter = EmailAdapter(name="email")
    result = adapter.health_check()
    assert result["ok"] is False


# --- Error path tests ---


def test_send_smtp_raises_connection_refused(email_adapter, mocker):
    email_adapter.connect()
    mocker.patch("smtplib.SMTP", side_effect=ConnectionRefusedError("Connection refused"))

    result = email_adapter.execute("send", {
        "to": "recipient@test.com",
        "subject": "Test",
        "body": "Hello",
    })

    assert result["ok"] is False
    assert "Connection refused" in result["error"]


def test_send_invalid_smtp_port(mocker):
    stored = {
        ("merkaba-ai", "integration:email:smtp_host"): "smtp.test.com",
        ("merkaba-ai", "integration:email:smtp_port"): "not_a_number",
        ("merkaba-ai", "integration:email:smtp_user"): "user@test.com",
        ("merkaba-ai", "integration:email:smtp_password"): "pass123",
        ("merkaba-ai", "integration:email:imap_host"): "imap.test.com",
        ("merkaba-ai", "integration:email:imap_user"): "user@test.com",
        ("merkaba-ai", "integration:email:imap_password"): "pass123",
    }
    mocker.patch(
        "merkaba.security.secrets.keyring.get_password",
        side_effect=lambda svc, key: stored.get((svc, key)),
    )
    adapter = EmailAdapter(name="email")
    adapter.connect()

    result = adapter.execute("send", {
        "to": "recipient@test.com",
        "subject": "Test",
        "body": "Hello",
    })

    assert result["ok"] is False
    assert "Invalid smtp_port" in result["error"]
    assert "not_a_number" in result["error"]


def test_read_inbox_imap_raises_exception(email_adapter, mocker):
    email_adapter.connect()
    mocker.patch("imaplib.IMAP4_SSL", side_effect=OSError("IMAP connection failed"))

    result = email_adapter.execute("read_inbox", {"limit": 5})

    assert result["ok"] is False
    assert "IMAP connection failed" in result["error"]
    assert result["emails"] == []


def test_parse_email_llm_returns_non_json(email_adapter, mocker):
    email_adapter.connect()

    mock_llm = MagicMock()
    mock_llm.chat.return_value = MagicMock(content="This is plain text, not JSON")
    mocker.patch(
        "merkaba.integrations.email_adapter.EmailAdapter._get_llm",
        return_value=mock_llm,
    )

    result = email_adapter.execute("parse_email", {
        "from": "customer@test.com",
        "subject": "Help",
        "body": "I need help with my order",
    })

    assert result["ok"] is False
    assert "parsed" in result
    assert result["parsed"]["raw_response"] == "This is plain text, not JSON"


def test_parse_email_llm_raises_connection_error(email_adapter, mocker):
    email_adapter.connect()

    mock_llm = MagicMock()
    mock_llm.chat.side_effect = ConnectionError("Ollama is down")
    mocker.patch(
        "merkaba.integrations.email_adapter.EmailAdapter._get_llm",
        return_value=mock_llm,
    )

    result = email_adapter.execute("parse_email", {
        "from": "customer@test.com",
        "subject": "Help",
        "body": "I need help with my order",
    })

    assert result["ok"] is False
    assert "Ollama is down" in result["error"]

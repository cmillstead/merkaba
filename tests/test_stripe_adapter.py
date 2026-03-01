# tests/test_stripe_adapter.py
from unittest.mock import MagicMock

import pytest

try:
    import keyring.errors
    HAS_DEPS = True
except ImportError:
    HAS_DEPS = False

pytestmark = pytest.mark.skipif(not HAS_DEPS, reason="Missing keyring")

from merkaba.integrations.stripe_adapter import StripeAdapter
from merkaba.integrations.base import ADAPTER_REGISTRY


def test_stripe_adapter_registered():
    assert "stripe" in ADAPTER_REGISTRY


@pytest.fixture
def stripe_adapter(mocker):
    stored = {
        ("merkaba-ai", "integration:stripe:api_key"): "sk_test_fake123",
    }
    mocker.patch(
        "merkaba.security.secrets.keyring.get_password",
        side_effect=lambda svc, key: stored.get((svc, key)),
    )
    return StripeAdapter(name="stripe")


def test_connect_success(stripe_adapter):
    assert stripe_adapter.connect() is True
    assert stripe_adapter.is_connected is True


def test_connect_fails_missing_key(mocker):
    mocker.patch("merkaba.security.secrets.keyring.get_password", return_value=None)
    adapter = StripeAdapter(name="stripe")
    assert adapter.connect() is False


def test_execute_get_balance(stripe_adapter, mocker):
    stripe_adapter.connect()
    mock_balance = MagicMock()
    mock_balance.available = [MagicMock(amount=10000, currency="usd")]
    mock_balance.pending = [MagicMock(amount=500, currency="usd")]
    mocker.patch("stripe.Balance.retrieve", return_value=mock_balance)

    result = stripe_adapter.execute("get_balance")
    assert result["ok"] is True
    assert result["available"][0]["amount"] == 10000


def test_execute_list_payments(stripe_adapter, mocker):
    stripe_adapter.connect()
    mock_charges = MagicMock()
    mock_charges.data = [
        MagicMock(id="ch_1", amount=2500, currency="usd", status="succeeded")
    ]
    mocker.patch("stripe.Charge.list", return_value=mock_charges)

    result = stripe_adapter.execute("list_payments", {"limit": 5})
    assert result["ok"] is True
    assert len(result["payments"]) == 1


def test_execute_get_customer(stripe_adapter, mocker):
    stripe_adapter.connect()
    mock_customer = MagicMock()
    mock_customer.id = "cus_123"
    mock_customer.email = "test@test.com"
    mock_customer.name = "Test User"
    mocker.patch("stripe.Customer.retrieve", return_value=mock_customer)

    result = stripe_adapter.execute("get_customer", {"customer_id": "cus_123"})
    assert result["ok"] is True
    assert result["customer"]["email"] == "test@test.com"


def test_execute_list_subscriptions(stripe_adapter, mocker):
    stripe_adapter.connect()
    mock_subs = MagicMock()
    mock_subs.data = [
        MagicMock(id="sub_1", status="active", current_period_end=1700000000)
    ]
    mocker.patch("stripe.Subscription.list", return_value=mock_subs)

    result = stripe_adapter.execute("list_subscriptions", {"limit": 5})
    assert result["ok"] is True
    assert len(result["subscriptions"]) == 1


def test_execute_unknown_action(stripe_adapter):
    stripe_adapter.connect()
    result = stripe_adapter.execute("create_charge")
    assert result["ok"] is False
    assert "Unknown action" in result["error"]


def test_health_check_connected(stripe_adapter, mocker):
    stripe_adapter.connect()
    mock_balance = MagicMock()
    mock_balance.available = [MagicMock(amount=0, currency="usd")]
    mocker.patch("stripe.Balance.retrieve", return_value=mock_balance)

    result = stripe_adapter.health_check()
    assert result["ok"] is True


def test_health_check_not_connected():
    adapter = StripeAdapter(name="stripe")
    result = adapter.health_check()
    assert result["ok"] is False


# --- Error path tests ---


def test_get_balance_exception(stripe_adapter, mocker):
    stripe_adapter.connect()
    mocker.patch("stripe.Balance.retrieve", side_effect=RuntimeError("API error"))

    result = stripe_adapter.execute("get_balance")
    assert result["ok"] is False
    assert "API error" in result["error"]


def test_list_payments_exception(stripe_adapter, mocker):
    stripe_adapter.connect()
    mocker.patch("stripe.Charge.list", side_effect=ConnectionError("Network down"))

    result = stripe_adapter.execute("list_payments", {"limit": 5})
    assert result["ok"] is False
    assert "Network down" in result["error"]


def test_get_customer_missing_customer_id(stripe_adapter):
    stripe_adapter.connect()

    result = stripe_adapter.execute("get_customer", {})
    assert result["ok"] is False
    assert result["error"] == "Missing customer_id"


def test_get_customer_exception(stripe_adapter, mocker):
    stripe_adapter.connect()
    mocker.patch(
        "stripe.Customer.retrieve",
        side_effect=RuntimeError("Customer not found"),
    )

    result = stripe_adapter.execute("get_customer", {"customer_id": "cus_bad"})
    assert result["ok"] is False
    assert "Customer not found" in result["error"]


def test_list_subscriptions_exception(stripe_adapter, mocker):
    stripe_adapter.connect()
    mocker.patch(
        "stripe.Subscription.list",
        side_effect=TimeoutError("Request timed out"),
    )

    result = stripe_adapter.execute("list_subscriptions", {"limit": 5})
    assert result["ok"] is False
    assert "Request timed out" in result["error"]


def test_get_invoice_missing_invoice_id(stripe_adapter):
    stripe_adapter.connect()

    result = stripe_adapter.execute("get_invoice", {})
    assert result["ok"] is False
    assert result["error"] == "Missing invoice_id"


def test_health_check_exception(stripe_adapter, mocker):
    stripe_adapter.connect()
    mocker.patch(
        "stripe.Balance.retrieve",
        side_effect=RuntimeError("Auth failed"),
    )

    result = stripe_adapter.health_check()
    assert result["ok"] is False
    assert result["adapter"] == "stripe"
    assert "Auth failed" in result["error"]

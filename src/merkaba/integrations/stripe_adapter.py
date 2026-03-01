# src/friday/integrations/stripe_adapter.py
"""Stripe integration adapter — read-only operations."""

import logging
from dataclasses import dataclass, field

import stripe

from friday.integrations.base import IntegrationAdapter, register_adapter
from friday.integrations.credentials import CredentialManager

logger = logging.getLogger(__name__)

REQUIRED_CREDENTIALS = ["api_key"]


@dataclass
class StripeAdapter(IntegrationAdapter):
    """Stripe adapter: read-only access to balances, payments, customers, subscriptions."""

    _creds: CredentialManager = field(default_factory=CredentialManager, init=False, repr=False)

    def connect(self) -> bool:
        ok, missing = self._creds.has_required("stripe", REQUIRED_CREDENTIALS)
        if not ok:
            logger.warning("Stripe adapter missing credentials: %s", missing)
            self._connected = False
            return False
        stripe.api_key = self._creds.get("stripe", "api_key")
        self._connected = True
        return True

    def execute(self, action: str, params: dict | None = None) -> dict:
        params = params or {}
        if action == "get_balance":
            return self._get_balance()
        elif action == "list_payments":
            return self._list_payments(params)
        elif action == "get_customer":
            return self._get_customer(params)
        elif action == "list_subscriptions":
            return self._list_subscriptions(params)
        elif action == "get_invoice":
            return self._get_invoice(params)
        else:
            return {"ok": False, "error": f"Unknown action: {action}"}

    def health_check(self) -> dict:
        if not self._connected:
            return {"ok": False, "adapter": "stripe", "error": "Not connected"}
        try:
            stripe.Balance.retrieve()
            return {"ok": True, "adapter": "stripe"}
        except Exception as e:
            return {"ok": False, "adapter": "stripe", "error": str(e)}

    def _get_balance(self) -> dict:
        try:
            balance = stripe.Balance.retrieve()
            return {
                "ok": True,
                "available": [{"amount": b.amount, "currency": b.currency} for b in balance.available],
                "pending": [{"amount": b.amount, "currency": b.currency} for b in balance.pending],
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _list_payments(self, params: dict) -> dict:
        try:
            limit = params.get("limit", 10)
            charges = stripe.Charge.list(limit=limit)
            return {
                "ok": True,
                "payments": [
                    {"id": c.id, "amount": c.amount, "currency": c.currency, "status": c.status}
                    for c in charges.data
                ],
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _get_customer(self, params: dict) -> dict:
        customer_id = params.get("customer_id")
        if not customer_id:
            return {"ok": False, "error": "Missing customer_id"}
        try:
            customer = stripe.Customer.retrieve(customer_id)
            return {
                "ok": True,
                "customer": {"id": customer.id, "email": customer.email, "name": customer.name},
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _list_subscriptions(self, params: dict) -> dict:
        try:
            limit = params.get("limit", 10)
            subs = stripe.Subscription.list(limit=limit)
            return {
                "ok": True,
                "subscriptions": [
                    {"id": s.id, "status": s.status, "current_period_end": s.current_period_end}
                    for s in subs.data
                ],
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _get_invoice(self, params: dict) -> dict:
        invoice_id = params.get("invoice_id")
        if not invoice_id:
            return {"ok": False, "error": "Missing invoice_id"}
        try:
            invoice = stripe.Invoice.retrieve(invoice_id)
            return {
                "ok": True,
                "invoice": {
                    "id": invoice.id,
                    "amount_due": invoice.amount_due,
                    "status": invoice.status,
                    "customer": invoice.customer,
                },
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}


register_adapter("stripe", StripeAdapter)

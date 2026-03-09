"""Mock Stripe integration for billing flows.

This module intentionally avoids the real Stripe SDK and provides a
fully in-memory mock client suitable for deterministic tests.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Dict, Optional


@dataclass
class MockPaymentIntent:
    """In-memory representation of a payment intent."""

    payment_intent_id: str
    organization_id: str
    amount_cents: int
    invoice_id: str
    client_secret: str
    status: str
    created_at: datetime


class MockStripeClient:
    """Small in-memory mock Stripe client used by tests."""

    def __init__(self) -> None:
        self.customers: Dict[str, str] = {}
        self.payment_intents: Dict[str, MockPaymentIntent] = {}

    def create_customer(self, organization_id: str, name: str, email: str) -> str:
        """Create (or return existing) customer for organization."""
        if organization_id in self.customers:
            return self.customers[organization_id]

        customer_id = f"cus_{uuid.uuid4().hex[:16]}"
        self.customers[organization_id] = customer_id
        return customer_id

    def create_payment_intent(
        self,
        organization_id: str,
        amount_cents: int,
        invoice_id: str,
    ) -> Dict[str, str]:
        """Create a mock payment intent and return public fields."""
        payment_intent_id = f"pi_{uuid.uuid4().hex[:16]}"
        client_secret = f"{payment_intent_id}_secret_{uuid.uuid4().hex[:24]}"
        self.payment_intents[payment_intent_id] = MockPaymentIntent(
            payment_intent_id=payment_intent_id,
            organization_id=organization_id,
            amount_cents=amount_cents,
            invoice_id=invoice_id,
            client_secret=client_secret,
            status="requires_confirmation",
            created_at=datetime.now(tz=UTC),
        )
        return {
            "client_secret": client_secret,
            "payment_intent_id": payment_intent_id,
        }

    def confirm_payment(self, payment_intent_id: str) -> bool:
        """Confirm a payment intent if it exists."""
        intent = self.payment_intents.get(payment_intent_id)
        if intent is None:
            return False

        intent.status = "succeeded"
        return True


class StripeIntegrationManager:
    """Facade for customer creation and payment-intent lifecycle."""

    def __init__(self, stripe_client: Optional[MockStripeClient] = None) -> None:
        self.client = stripe_client or MockStripeClient()
        self._customer_by_org: Dict[str, str] = {}

    def create_or_get_customer(self, organization_id: str, name: str, email: str) -> str:
        """Create or fetch a Stripe customer mapping for organization."""
        if organization_id in self._customer_by_org:
            return self._customer_by_org[organization_id]

        customer_id = self.client.create_customer(organization_id, name, email)
        self._customer_by_org[organization_id] = customer_id
        return customer_id

    def create_payment_intent(
        self,
        organization_id: str,
        amount_cents: int,
        invoice_id: str,
    ) -> Dict[str, str]:
        """Create a payment intent for a monthly invoice."""
        return self.client.create_payment_intent(
            organization_id=organization_id,
            amount_cents=amount_cents,
            invoice_id=invoice_id,
        )

    def confirm_payment(self, payment_intent_id: str) -> bool:
        """Confirm a payment intent."""
        return self.client.confirm_payment(payment_intent_id)


_stripe_manager: Optional[StripeIntegrationManager] = None


def get_stripe_integration_manager(
    stripe_client: Optional[MockStripeClient] = None,
) -> StripeIntegrationManager:
    """Return (or create) the global :class:`StripeIntegrationManager`."""
    global _stripe_manager
    if _stripe_manager is None:
        _stripe_manager = StripeIntegrationManager(stripe_client)
    return _stripe_manager


def reset_stripe_integration_manager() -> None:
    """Reset stripe manager singleton (for tests)."""
    global _stripe_manager
    _stripe_manager = None

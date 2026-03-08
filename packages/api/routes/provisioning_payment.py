"""Payment consent provisioning flow — plan selection + confirmation.

Handles the payment consent flow:
1. Agent requests a plan for a service (free, pro, enterprise)
2. Handler generates a payment/checkout URL for the human to visit
3. Human completes payment and provides a confirmation token
4. Handler verifies payment and marks the flow complete

No blocking waits — the payment URL is returned immediately.
"""

from __future__ import annotations

from typing import Any, Dict, Optional
from urllib.parse import urlencode

from schemas.provisioning import (
    FlowState,
    FlowType,
    ProvisioningFlowStore,
)


# Payment / billing URLs per provider
_PAYMENT_URLS: Dict[str, str] = {
    "stripe": "https://dashboard.stripe.com/settings/billing",
    "sendgrid": "https://app.sendgrid.com/settings/billing",
    "twilio": "https://www.twilio.com/console/billing",
    "github": "https://github.com/settings/billing",
    "slack": "https://slack.com/intl/en-gb/pricing",
}

# Valid plans per provider
_VALID_PLANS: Dict[str, set[str]] = {
    "stripe": {"free", "pro", "enterprise"},
    "sendgrid": {"free", "essentials", "pro"},
    "twilio": {"pay-as-you-go", "enterprise"},
    "github": {"free", "pro", "team", "enterprise"},
    "slack": {"free", "pro", "business+", "enterprise"},
}


class PaymentFlowHandler:
    """Payment consent and plan activation."""

    def __init__(self, store: ProvisioningFlowStore) -> None:
        self.store = store

    # ------------------------------------------------------------------
    # Start
    # ------------------------------------------------------------------

    async def start_payment(
        self,
        agent_id: str,
        service: str,
        plan: str,
    ) -> Dict[str, Any]:
        """Initiate a payment/plan-selection flow.

        Returns:
            ``{"flow_id", "payment_url", "plan", "expires_in"}``
        """
        # Validate service
        if service not in _PAYMENT_URLS:
            return {
                "flow_id": None,
                "status": "failed",
                "error": f"Service '{service}' does not support payment flows",
            }

        # Validate plan
        valid = _VALID_PLANS.get(service, set())
        if plan not in valid:
            return {
                "flow_id": None,
                "status": "failed",
                "error": (
                    f"Plan '{plan}' is not valid for '{service}'. "
                    f"Valid plans: {sorted(valid)}"
                ),
            }

        # Create flow
        flow_id = await self.store.create_flow(
            agent_id=agent_id,
            service=service,
            flow_type=FlowType.PAYMENT,
            payload={"plan": plan},
        )

        # Build payment URL
        base_url = _PAYMENT_URLS[service]
        params = urlencode({"plan": plan})
        payment_url = f"{base_url}?{params}"
        await self.store.set_human_action_url(flow_id, payment_url)

        return {
            "flow_id": flow_id,
            "status": "link_provided",
            "payment_url": payment_url,
            "plan": plan,
            "expires_in": 3600,
        }

    # ------------------------------------------------------------------
    # Confirm
    # ------------------------------------------------------------------

    async def confirm_payment(
        self,
        flow_id: str,
        payment_confirmation_token: str,
    ) -> Dict[str, Any]:
        """Confirm payment after the human completes checkout.

        Args:
            flow_id: The provisioning flow ID.
            payment_confirmation_token: Token or ID from the payment
                processor (e.g. Stripe checkout session ID).

        Returns:
            ``{"status", "message"}`` or ``{"status", "error"}``.
        """
        flow = await self.store.get_flow(flow_id)
        if flow is None:
            return {"status": "failed", "error": "flow_not_found"}

        # Check expiration
        if await self.store.check_expiration(flow_id):
            return {"status": "failed", "error": "flow_expired"}

        # Check current state
        if flow.state in (FlowState.COMPLETE.value, FlowState.FAILED.value, FlowState.EXPIRED.value):
            return {"status": "failed", "error": f"flow_already_{flow.state}"}

        # Verify token is present
        if not payment_confirmation_token:
            return {"status": "failed", "error": "payment_confirmation_token required"}

        # Verify payment with provider (mock for Phase 2.1)
        verified = await self._verify_payment(flow.service, payment_confirmation_token)
        if not verified:
            return {"status": "failed", "error": "payment_verification_failed"}

        # Mark complete
        await self.store.update_flow_state(
            flow_id,
            FlowState.COMPLETE,
            callback_data={
                "payment_confirmed": True,
                "payment_token": payment_confirmation_token,
                "plan": flow.payload.get("plan", "unknown"),
            },
        )

        return {
            "status": "complete",
            "message": "Payment confirmed, service activated",
        }

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _verify_payment(self, service: str, token: str) -> bool:
        """Verify a payment confirmation token with the provider.

        In production this calls the provider's API (e.g. Stripe
        checkout session retrieval).  For now accepts any non-empty
        token.
        """
        return bool(token)

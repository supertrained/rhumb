"""Signup provisioning flow — email-based service registration.

Handles the agent-initiated signup process:
1. Agent requests signup for a service (email + name)
2. Handler generates a signup URL for the human to visit
3. Human completes registration and returns with a verification code
4. Handler verifies the code and marks the flow complete

No blocking waits — the flow returns an action URL and the agent
polls for completion or receives a callback.
"""

from __future__ import annotations

from typing import Any, Dict, Optional
from urllib.parse import quote_plus

from schemas.provisioning import (
    FlowState,
    FlowType,
    ProvisioningFlowStore,
)
from services.service_slugs import public_service_slug


# Known signup URLs per provider
_SIGNUP_URLS: Dict[str, str] = {
    "stripe": "https://dashboard.stripe.com/register",
    "slack": "https://slack.com/get-started",
    "sendgrid": "https://signup.sendgrid.com/",
    "github": "https://github.com/signup",
    "twilio": "https://www.twilio.com/try-twilio",
}


class SignupFlowHandler:
    """Initiate and complete email-based signup flows."""

    def __init__(self, store: ProvisioningFlowStore) -> None:
        self.store = store

    # ------------------------------------------------------------------
    # Start
    # ------------------------------------------------------------------

    async def start_signup(
        self,
        agent_id: str,
        service: str,
        email: str,
        name: str,
    ) -> Dict[str, Any]:
        """Start a signup flow.

        Returns:
            ``{"flow_id", "status", "action_url", "message"}``
        """
        public_service = public_service_slug(service) or str(service).strip().lower()

        # Validate service
        base_url = _SIGNUP_URLS.get(public_service)
        if base_url is None:
            return {
                "flow_id": None,
                "status": "failed",
                "action_url": None,
                "message": f"Service '{public_service}' does not support signup flows",
            }

        # Create flow record
        flow_id = await self.store.create_flow(
            agent_id=agent_id,
            service=public_service,
            flow_type=FlowType.SIGNUP,
            payload={"email": email, "name": name},
        )

        # Build signup URL with pre-filled email where possible
        signup_url = f"{base_url}?email={quote_plus(email)}"
        await self.store.set_human_action_url(flow_id, signup_url)

        return {
            "flow_id": flow_id,
            "status": "link_provided",
            "action_url": signup_url,
            "message": (
                f"Visit {signup_url} and complete signup. "
                "Return here with the verification code."
            ),
        }

    # ------------------------------------------------------------------
    # Verify
    # ------------------------------------------------------------------

    async def verify_signup(
        self,
        flow_id: Any,
        *,
        email_code: Optional[Any] = None,
        verification_token: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Complete a signup flow after the human has verified their email.

        Accepts either an ``email_code`` or a ``verification_token`` (at
        least one is required).

        Returns:
            ``{"status", "message"}`` or ``{"status", "error"}``.
        """
        normalized_flow_id = flow_id.strip() if isinstance(flow_id, str) else ""
        if not normalized_flow_id:
            return {"status": "failed", "error": "flow_id required"}

        # Require at least one verification artifact before opening flow state.
        normalized_email_code = email_code.strip() if isinstance(email_code, str) else ""
        normalized_verification_token = (
            verification_token.strip() if isinstance(verification_token, str) else ""
        )
        if not normalized_email_code and not normalized_verification_token:
            return {"status": "failed", "error": "email_code or verification_token required"}

        flow = await self.store.get_flow(normalized_flow_id)
        if flow is None:
            return {"status": "failed", "error": "flow_not_found"}

        # Check expiration
        if await self.store.check_expiration(normalized_flow_id):
            return {"status": "failed", "error": "flow_expired"}

        # Check current state allows completion
        if flow.state in (FlowState.COMPLETE.value, FlowState.FAILED.value, FlowState.EXPIRED.value):
            return {"status": "failed", "error": f"flow_already_{flow.state}"}

        # Mark complete with callback data
        callback: Dict[str, Any] = {}
        if normalized_email_code:
            callback["email_code"] = normalized_email_code
        if normalized_verification_token:
            callback["verification_token"] = normalized_verification_token

        await self.store.update_flow_state(
            normalized_flow_id,
            FlowState.COMPLETE,
            callback_data=callback,
        )

        return {"status": "complete", "message": "Signup verified"}

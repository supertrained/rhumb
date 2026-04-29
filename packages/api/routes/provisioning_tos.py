"""Terms of Service acceptance provisioning flow.

Handles the ToS acceptance process:
1. Agent requests ToS for a service
2. Handler fetches (or caches) the provider's ToS text
3. Returns the text + a SHA-256 hash + an acceptance URL
4. Human reviews and accepts
5. Handler records acceptance with the ToS hash for audit

No blocking waits — the acceptance URL is returned immediately.
"""

from __future__ import annotations

import hashlib
from typing import Any, Dict, Optional

from schemas.provisioning import (
    FlowState,
    FlowType,
    ProvisioningFlowStore,
)
from services.service_slugs import public_service_slug


# Cached / mock ToS text per provider (Phase 2.2 will fetch live)
_TOS_TEXTS: Dict[str, str] = {
    "stripe": (
        "Stripe Terms of Service\n\n"
        "By using Stripe, you agree to our payment processing terms, "
        "including our privacy policy, acceptable use policy, and "
        "data processing agreement. Full terms at https://stripe.com/legal."
    ),
    "slack": (
        "Slack Terms of Service\n\n"
        "By using Slack, you agree to our terms of service, privacy "
        "policy, and acceptable use policy. You are responsible for "
        "all activity under your workspace. Full terms at https://slack.com/terms."
    ),
    "sendgrid": (
        "Twilio SendGrid Terms of Service\n\n"
        "By using SendGrid, you agree to Twilio's terms of service, "
        "acceptable use policy, and anti-spam policy. Full terms at "
        "https://www.twilio.com/en-us/legal/tos."
    ),
    "github": (
        "GitHub Terms of Service\n\n"
        "By using GitHub, you agree to our terms of service, privacy "
        "statement, and acceptable use policies. Full terms at "
        "https://docs.github.com/en/site-policy/github-terms."
    ),
    "twilio": (
        "Twilio Terms of Service\n\n"
        "By using Twilio, you agree to our terms of service, acceptable "
        "use policy, and data protection addendum. Full terms at "
        "https://www.twilio.com/en-us/legal/tos."
    ),
}

_ACCEPTANCE_BASE = "https://api.rhumb.dev"


class ToSFlowHandler:
    """Terms of Service presentation and acceptance."""

    def __init__(
        self,
        store: ProvisioningFlowStore,
        *,
        acceptance_base: str = _ACCEPTANCE_BASE,
    ) -> None:
        self.store = store
        self.acceptance_base = acceptance_base

    # ------------------------------------------------------------------
    # Start
    # ------------------------------------------------------------------

    async def start_tos(
        self,
        agent_id: str,
        service: str,
    ) -> Dict[str, Any]:
        """Start a ToS acceptance flow.

        Returns:
            ``{"flow_id", "tos_text", "tos_hash", "acceptance_url"}``
        """
        public_service = public_service_slug(service) or str(service).strip().lower()
        tos_text = await self._fetch_tos(public_service)
        if tos_text is None:
            return {
                "flow_id": None,
                "status": "failed",
                "error": f"No ToS available for service '{public_service}'",
            }

        tos_hash = hashlib.sha256(tos_text.encode()).hexdigest()

        # Create flow
        flow_id = await self.store.create_flow(
            agent_id=agent_id,
            service=public_service,
            flow_type=FlowType.TOS,
            payload={"tos_hash": tos_hash},
        )

        acceptance_url = (
            f"{self.acceptance_base}/v1/provisioning/tos/{flow_id}/accept"
        )
        await self.store.set_human_action_url(flow_id, acceptance_url)

        return {
            "flow_id": flow_id,
            "tos_text": tos_text,
            "tos_hash": tos_hash,
            "acceptance_url": acceptance_url,
        }

    # ------------------------------------------------------------------
    # Accept
    # ------------------------------------------------------------------

    async def accept_tos(
        self,
        flow_id: str,
        *,
        tos_hash: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Accept the Terms of Service.

        Args:
            flow_id: The provisioning flow ID.
            tos_hash: Optional hash of the ToS text the human reviewed.
                If provided, it is compared against the stored hash to
                ensure the human accepted the current version.

        Returns:
            ``{"status", "message"}`` or ``{"status", "error"}``.
        """
        normalized_flow_id = str(flow_id or "").strip()
        if not normalized_flow_id:
            return {"status": "failed", "error": "flow_id required"}

        flow = await self.store.get_flow(normalized_flow_id)
        if flow is None:
            return {"status": "failed", "error": "flow_not_found"}

        # Check expiration
        if await self.store.check_expiration(normalized_flow_id):
            return {"status": "failed", "error": "flow_expired"}

        if flow.state in (FlowState.COMPLETE.value, FlowState.FAILED.value, FlowState.EXPIRED.value):
            return {"status": "failed", "error": f"flow_already_{flow.state}"}

        # Verify hash if provided
        if tos_hash is not None:
            stored_hash = flow.payload.get("tos_hash")
            if stored_hash and tos_hash != stored_hash:
                return {
                    "status": "failed",
                    "error": "tos_hash_mismatch — ToS may have been updated",
                }

        # Mark complete
        await self.store.update_flow_state(
            normalized_flow_id,
            FlowState.COMPLETE,
            callback_data={
                "accepted": True,
                "accepted_tos_hash": flow.payload.get("tos_hash", ""),
            },
        )

        return {"status": "complete", "message": "ToS accepted"}

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _fetch_tos(self, service: str) -> Optional[str]:
        """Fetch the ToS text for a service.

        In production this may scrape or call a provider API.
        For now uses the cached text from ``_TOS_TEXTS``.
        """
        return _TOS_TEXTS.get(service)

"""Provisioning orchestrator — chains multi-step flows per service.

Each service has a defined sequence of provisioning steps (e.g.
SendGrid: signup → payment → tos).  The orchestrator manages the
sequence, advances through steps as each completes, and reports
overall provisioning status.

No blocking waits — the orchestrator returns the next action URL
and the agent polls or receives callbacks.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from schemas.provisioning import (
    FlowState,
    FlowType,
    ProvisioningFlowStore,
)
from routes.provisioning_oauth import OAuthFlowHandler
from routes.provisioning_payment import PaymentFlowHandler
from routes.provisioning_signup import SignupFlowHandler
from routes.provisioning_tos import ToSFlowHandler
from services.proxy_credentials import CredentialStore


class ProvisioningOrchestrator:
    """Orchestrate multi-step provisioning sequences."""

    # Default flow sequences per service
    FLOW_SEQUENCES: Dict[str, List[FlowType]] = {
        "stripe": [FlowType.OAUTH, FlowType.TOS],
        "slack": [FlowType.OAUTH, FlowType.TOS],
        "sendgrid": [FlowType.SIGNUP, FlowType.PAYMENT, FlowType.TOS],
        "github": [FlowType.OAUTH, FlowType.TOS],
        "twilio": [FlowType.SIGNUP, FlowType.PAYMENT, FlowType.TOS],
    }

    def __init__(
        self,
        store: ProvisioningFlowStore,
        credential_store: Optional[CredentialStore] = None,
    ) -> None:
        self.store = store
        self.credential_store = credential_store

        # Handlers
        self._signup = SignupFlowHandler(store)
        self._oauth = OAuthFlowHandler(store, credential_store)
        self._payment = PaymentFlowHandler(store)
        self._tos = ToSFlowHandler(store)

    # ------------------------------------------------------------------
    # Start
    # ------------------------------------------------------------------

    async def start_provisioning(
        self,
        agent_id: str,
        service: str,
        *,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Start the full provisioning sequence for a service.

        Args:
            agent_id: The agent requesting provisioning.
            service: Target service to provision.
            context: Optional context dict with keys like ``email``,
                ``name``, ``scopes``, ``plan`` needed by sub-flows.

        Returns:
            ``{"status", "sequence", "current_step", "flow_id",
              "action_url", …}``
        """
        sequence = self.FLOW_SEQUENCES.get(service)
        if sequence is None:
            return {
                "status": "failed",
                "error": f"Service '{service}' is not supported for provisioning",
            }

        ctx = context or {}

        # Start first step
        first_type = sequence[0]
        result = await self._start_step(agent_id, service, first_type, ctx)

        # Record sequence in store
        await self.store.set_provisioning_sequence(
            agent_id=agent_id,
            service=service,
            sequence=sequence,
            current_index=0,
        )

        return {
            "status": "in_progress",
            "sequence": [ft.value for ft in sequence],
            "current_step": first_type.value,
            "current_step_index": 0,
            "total_steps": len(sequence),
            "flow_id": result.get("flow_id"),
            "action_url": result.get("action_url") or result.get("authorization_url") or result.get("payment_url"),
            "step_result": result,
        }

    # ------------------------------------------------------------------
    # Advance
    # ------------------------------------------------------------------

    async def advance_provisioning(
        self,
        agent_id: str,
        service: str,
        *,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Advance to the next step after the current flow completes.

        Returns:
            ``{"status": "in_progress", "current_step", "action_url", …}``
            or ``{"status": "complete"}`` when all steps are done.
        """
        seq_data = await self.store.get_provisioning_sequence(agent_id, service)
        if seq_data is None:
            return {"status": "failed", "error": "no_provisioning_in_progress"}

        sequence: List[FlowType] = seq_data["sequence"]
        current_index: int = seq_data["current_index"]
        next_index = current_index + 1

        if next_index >= len(sequence):
            return {
                "status": "complete",
                "message": f"Provisioning complete for {service}",
                "steps_completed": len(sequence),
            }

        ctx = context or {}
        next_type = sequence[next_index]
        result = await self._start_step(agent_id, service, next_type, ctx)

        # Update sequence position
        await self.store.set_provisioning_sequence(
            agent_id=agent_id,
            service=service,
            sequence=sequence,
            current_index=next_index,
        )

        return {
            "status": "in_progress",
            "current_step": next_type.value,
            "current_step_index": next_index,
            "total_steps": len(sequence),
            "flow_id": result.get("flow_id"),
            "action_url": result.get("action_url") or result.get("authorization_url") or result.get("payment_url"),
            "step_result": result,
        }

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    async def get_provisioning_status(
        self,
        agent_id: str,
        service: str,
    ) -> Dict[str, Any]:
        """Get current provisioning status for an agent+service pair.

        Returns:
            ``{"status", "current_step", "steps_completed", "total_steps", …}``
        """
        seq_data = await self.store.get_provisioning_sequence(agent_id, service)
        if seq_data is None:
            return {"status": "not_started", "service": service}

        sequence: List[FlowType] = seq_data["sequence"]
        current_index: int = seq_data["current_index"]

        return {
            "status": "in_progress" if current_index < len(sequence) - 1 else "final_step",
            "service": service,
            "current_step": sequence[current_index].value,
            "current_step_index": current_index,
            "total_steps": len(sequence),
            "sequence": [ft.value for ft in sequence],
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _start_step(
        self,
        agent_id: str,
        service: str,
        flow_type: FlowType,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Start a specific provisioning step."""
        if flow_type == FlowType.SIGNUP:
            return await self._signup.start_signup(
                agent_id=agent_id,
                service=service,
                email=context.get("email", f"agent@{service}.example.com"),
                name=context.get("name", agent_id),
            )
        elif flow_type == FlowType.OAUTH:
            return await self._oauth.start_oauth(
                agent_id=agent_id,
                service=service,
                scopes=context.get("scopes", ["read", "write"]),
            )
        elif flow_type == FlowType.PAYMENT:
            return await self._payment.start_payment(
                agent_id=agent_id,
                service=service,
                plan=context.get("plan", "free"),
            )
        elif flow_type == FlowType.TOS:
            return await self._tos.start_tos(
                agent_id=agent_id,
                service=service,
            )
        else:
            return {
                "flow_id": None,
                "status": "failed",
                "error": f"Unsupported flow type: {flow_type.value}",
            }

    # ------------------------------------------------------------------
    # Handler accessors (for direct flow completion from tests)
    # ------------------------------------------------------------------

    @property
    def signup_handler(self) -> SignupFlowHandler:
        """Return the signup flow handler."""
        return self._signup

    @property
    def oauth_handler(self) -> OAuthFlowHandler:
        """Return the OAuth flow handler."""
        return self._oauth

    @property
    def payment_handler(self) -> PaymentFlowHandler:
        """Return the payment flow handler."""
        return self._payment

    @property
    def tos_handler(self) -> ToSFlowHandler:
        """Return the ToS flow handler."""
        return self._tos

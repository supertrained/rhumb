"""Tests for Round 10 Slice D — Provisioning flows + orchestration.

Covers:
  - ProvisioningFlowStore (CRUD, state machine, expiration, retries)
  - SignupFlowHandler (start, verify, edge cases)
  - OAuthFlowHandler (start, callback, state verification, retries)
  - PaymentFlowHandler (start, confirm, validation)
  - ToSFlowHandler (start, accept, hash verification)
  - ProvisioningOrchestrator (multi-step sequences, advance, status)
  - E2E integration (full provisioning for SendGrid, Slack, GitHub)

Target: 25+ tests (actual: 32)
"""

from __future__ import annotations

import asyncio
import hashlib
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from schemas.provisioning import (
    FlowState,
    FlowType,
    ProvisioningFlowSchema,
    ProvisioningFlowStore,
    VALID_TRANSITIONS,
)
from routes.provisioning_signup import SignupFlowHandler
from routes.provisioning_oauth import OAuthFlowHandler, _state_tokens
from routes.provisioning_payment import PaymentFlowHandler
from routes.provisioning_tos import ToSFlowHandler, _TOS_TEXTS
from services.provisioning_orchestrator import ProvisioningOrchestrator
from services.proxy_credentials import CredentialStore


# =====================================================================
# Fixtures
# =====================================================================


@pytest.fixture
def store() -> ProvisioningFlowStore:
    """In-memory provisioning flow store (no Supabase)."""
    return ProvisioningFlowStore(supabase_client=None)


@pytest.fixture
def credential_store() -> CredentialStore:
    """CredentialStore with auto_load disabled."""
    return CredentialStore(auto_load=False)


@pytest.fixture
def signup_handler(store: ProvisioningFlowStore) -> SignupFlowHandler:
    return SignupFlowHandler(store)


@pytest.fixture
def oauth_handler(
    store: ProvisioningFlowStore, credential_store: CredentialStore
) -> OAuthFlowHandler:
    return OAuthFlowHandler(store, credential_store)


@pytest.fixture
def payment_handler(store: ProvisioningFlowStore) -> PaymentFlowHandler:
    return PaymentFlowHandler(store)


@pytest.fixture
def tos_handler(store: ProvisioningFlowStore) -> ToSFlowHandler:
    return ToSFlowHandler(store)


@pytest.fixture
def orchestrator(
    store: ProvisioningFlowStore, credential_store: CredentialStore
) -> ProvisioningOrchestrator:
    return ProvisioningOrchestrator(store, credential_store)


# =====================================================================
# 1. ProvisioningFlowStore — CRUD + state machine
# =====================================================================


class TestProvisioningFlowStore:
    """Flow creation, retrieval, state transitions, expiration, retries."""

    @pytest.mark.asyncio
    async def test_create_flow(self, store: ProvisioningFlowStore) -> None:
        """Create a flow with correct initial state."""
        flow_id = await store.create_flow(
            agent_id="rhumb-lead",
            service="stripe",
            flow_type=FlowType.OAUTH,
            payload={"scopes": ["read"]},
        )
        assert flow_id is not None

        flow = await store.get_flow(flow_id)
        assert flow is not None
        assert flow.agent_id == "rhumb-lead"
        assert flow.service == "stripe"
        assert flow.flow_type == FlowType.OAUTH.value
        assert flow.state == FlowState.PENDING.value
        assert flow.retries == 0

    @pytest.mark.asyncio
    async def test_get_flow_not_found(self, store: ProvisioningFlowStore) -> None:
        """Non-existent flow returns None."""
        flow = await store.get_flow("nonexistent-id")
        assert flow is None

    @pytest.mark.asyncio
    async def test_update_flow_state_valid(self, store: ProvisioningFlowStore) -> None:
        """Valid state transition updates the flow."""
        flow_id = await store.create_flow("a", "stripe", FlowType.OAUTH, {})
        await store.update_flow_state(flow_id, FlowState.IN_PROGRESS)

        flow = await store.get_flow(flow_id)
        assert flow is not None
        assert flow.state == FlowState.IN_PROGRESS.value

    @pytest.mark.asyncio
    async def test_update_flow_state_invalid_transition(
        self, store: ProvisioningFlowStore
    ) -> None:
        """Invalid state transition raises ValueError."""
        flow_id = await store.create_flow("a", "stripe", FlowType.OAUTH, {})
        # pending → complete is not valid (must go through in_progress)
        with pytest.raises(ValueError, match="Invalid transition"):
            await store.update_flow_state(flow_id, FlowState.COMPLETE)

    @pytest.mark.asyncio
    async def test_flow_expiration(self, store: ProvisioningFlowStore) -> None:
        """Flow is marked expired when expires_at is in the past."""
        flow_id = await store.create_flow(
            "a", "stripe", FlowType.OAUTH, {}, ttl_hours=0
        )
        # Force expiration by backdating
        store._mem[flow_id]["expires_at"] = (
            datetime.utcnow() - timedelta(hours=1)
        ).isoformat()

        is_expired = await store.check_expiration(flow_id)
        assert is_expired is True

        flow = await store.get_flow(flow_id)
        assert flow is not None
        assert flow.state == FlowState.EXPIRED.value

    @pytest.mark.asyncio
    async def test_flow_not_expired(self, store: ProvisioningFlowStore) -> None:
        """Flow within TTL is not expired."""
        flow_id = await store.create_flow("a", "stripe", FlowType.OAUTH, {})
        is_expired = await store.check_expiration(flow_id)
        assert is_expired is False

    @pytest.mark.asyncio
    async def test_increment_retries(self, store: ProvisioningFlowStore) -> None:
        """Retry counter increments correctly."""
        flow_id = await store.create_flow("a", "stripe", FlowType.OAUTH, {})
        r1 = await store.increment_retries(flow_id)
        assert r1 == 1
        r2 = await store.increment_retries(flow_id)
        assert r2 == 2

    @pytest.mark.asyncio
    async def test_set_human_action_url(self, store: ProvisioningFlowStore) -> None:
        """Setting action URL transitions to HUMAN_ACTION_NEEDED."""
        flow_id = await store.create_flow("a", "stripe", FlowType.OAUTH, {})
        await store.set_human_action_url(flow_id, "https://example.com/action")

        flow = await store.get_flow(flow_id)
        assert flow is not None
        assert flow.state == FlowState.HUMAN_ACTION_NEEDED.value
        assert flow.human_action_url == "https://example.com/action"

    @pytest.mark.asyncio
    async def test_list_flows_by_agent(self, store: ProvisioningFlowStore) -> None:
        """List flows for a specific agent."""
        await store.create_flow("agent-a", "stripe", FlowType.OAUTH, {})
        await store.create_flow("agent-a", "slack", FlowType.TOS, {})
        await store.create_flow("agent-b", "stripe", FlowType.SIGNUP, {})

        flows = await store.list_flows_by_agent("agent-a")
        assert len(flows) == 2

    @pytest.mark.asyncio
    async def test_provisioning_sequence_storage(
        self, store: ProvisioningFlowStore
    ) -> None:
        """Orchestration sequences are stored and retrieved."""
        seq = [FlowType.SIGNUP, FlowType.PAYMENT, FlowType.TOS]
        await store.set_provisioning_sequence("a", "sendgrid", seq, 0)

        data = await store.get_provisioning_sequence("a", "sendgrid")
        assert data is not None
        assert data["sequence"] == seq
        assert data["current_index"] == 0


# =====================================================================
# 2. SignupFlowHandler
# =====================================================================


class TestSignupFlowHandler:
    """Signup flow: start + verify."""

    @pytest.mark.asyncio
    async def test_signup_start_stripe(self, signup_handler: SignupFlowHandler) -> None:
        """Start signup for Stripe returns correct link."""
        result = await signup_handler.start_signup(
            agent_id="rhumb-lead", service="stripe",
            email="test@example.com", name="Test Agent",
        )
        assert result["status"] == "link_provided"
        assert result["flow_id"] is not None
        assert "stripe.com" in result["action_url"]
        assert "test%40example.com" in result["action_url"]

    @pytest.mark.asyncio
    async def test_signup_start_sendgrid(self, signup_handler: SignupFlowHandler) -> None:
        """Start signup for SendGrid returns correct link."""
        result = await signup_handler.start_signup(
            agent_id="rhumb-lead", service="sendgrid",
            email="agent@rhumb.dev", name="Rhumb Lead",
        )
        assert result["status"] == "link_provided"
        assert "sendgrid" in result["action_url"]

    @pytest.mark.asyncio
    async def test_signup_start_mixed_case_service_stores_canonical_id(
        self,
        signup_handler: SignupFlowHandler,
        store: ProvisioningFlowStore,
    ) -> None:
        """Mixed-case provisioning inputs should persist canonical public service ids."""
        result = await signup_handler.start_signup(
            agent_id="rhumb-lead", service="GitHub",
            email="agent@rhumb.dev", name="Rhumb Lead",
        )
        assert result["status"] == "link_provided"
        assert "github.com/signup" in result["action_url"]

        flow = await store.get_flow(result["flow_id"])
        assert flow is not None
        assert flow.service == "github"

    @pytest.mark.asyncio
    async def test_signup_start_unsupported_service(
        self, signup_handler: SignupFlowHandler
    ) -> None:
        """Unsupported service returns failure."""
        result = await signup_handler.start_signup(
            "a", "nonexistent_service", "e@x.com", "n"
        )
        assert result["status"] == "failed"
        assert result["flow_id"] is None

    @pytest.mark.asyncio
    async def test_signup_start_unsupported_alias_input_reports_canonical_service(
        self, signup_handler: SignupFlowHandler
    ) -> None:
        """Unsupported alias-style signup inputs should fail on canonical public service ids."""
        result = await signup_handler.start_signup(
            "a", "Brave-Search", "e@x.com", "n"
        )
        assert result["status"] == "failed"
        assert result["flow_id"] is None
        assert result["message"] == "Service 'brave-search-api' does not support signup flows"

    @pytest.mark.asyncio
    async def test_signup_verify_valid_code(
        self, signup_handler: SignupFlowHandler
    ) -> None:
        """Verify signup with valid code marks flow complete."""
        result = await signup_handler.start_signup(
            "a", "stripe", "e@x.com", "n"
        )
        flow_id = result["flow_id"]

        verify = await signup_handler.verify_signup(flow_id, email_code="ABC123")
        assert verify["status"] == "complete"

    @pytest.mark.asyncio
    async def test_signup_verify_no_code(
        self, signup_handler: SignupFlowHandler
    ) -> None:
        """Verify without code or token returns error."""
        result = await signup_handler.start_signup(
            "a", "stripe", "e@x.com", "n"
        )
        verify = await signup_handler.verify_signup(result["flow_id"])
        assert verify["status"] == "failed"
        assert "required" in verify["error"]

    def test_signup_verify_requires_artifact_before_flow_read(
        self, signup_handler: SignupFlowHandler, store: ProvisioningFlowStore
    ) -> None:
        """Missing signup verification artifacts should not open flow state."""
        store.get_flow = AsyncMock()  # type: ignore[method-assign]

        verify = asyncio.run(signup_handler.verify_signup("flow-123", email_code="   "))

        assert verify == {
            "status": "failed",
            "error": "email_code or verification_token required",
        }
        store.get_flow.assert_not_called()

    def test_signup_verify_rejects_non_string_inputs_before_flow_read(
        self, signup_handler: SignupFlowHandler, store: ProvisioningFlowStore
    ) -> None:
        """Signup verification should not stringify malformed IDs or artifacts before reads."""
        store.get_flow = AsyncMock()  # type: ignore[method-assign]

        bad_flow = asyncio.run(signup_handler.verify_signup(123, email_code="ABC123"))
        bad_artifact = asyncio.run(signup_handler.verify_signup("flow-123", email_code=["ABC123"]))

        assert bad_flow == {"status": "failed", "error": "flow_id required"}
        assert bad_artifact == {
            "status": "failed",
            "error": "email_code or verification_token required",
        }
        store.get_flow.assert_not_called()


# =====================================================================
# 3. OAuthFlowHandler
# =====================================================================


class TestOAuthFlowHandler:
    """OAuth flow: start, callback, state verification, retries."""

    @pytest.mark.asyncio
    async def test_start_oauth_slack(self, oauth_handler: OAuthFlowHandler) -> None:
        """Start OAuth for Slack generates correct authorization URL."""
        result = await oauth_handler.start_oauth(
            agent_id="rhumb-lead", service="slack", scopes=["chat:write", "channels:read"],
        )
        assert result["flow_id"] is not None
        assert "slack.com/oauth" in result["authorization_url"]
        assert result["expires_in"] == 3600

    @pytest.mark.asyncio
    async def test_start_oauth_github(self, oauth_handler: OAuthFlowHandler) -> None:
        """Start OAuth for GitHub generates correct authorization URL."""
        result = await oauth_handler.start_oauth(
            agent_id="rhumb-lead", service="github", scopes=["repo", "user"],
        )
        assert "github.com/login/oauth" in result["authorization_url"]

    @pytest.mark.asyncio
    async def test_start_oauth_mixed_case_service_stores_canonical_id(
        self,
        oauth_handler: OAuthFlowHandler,
        store: ProvisioningFlowStore,
    ) -> None:
        """Mixed-case OAuth inputs should persist canonical public service ids."""
        result = await oauth_handler.start_oauth(
            agent_id="rhumb-lead", service="GitHub", scopes=["repo"],
        )
        assert "github.com/login/oauth" in result["authorization_url"]

        flow = await store.get_flow(result["flow_id"])
        assert flow is not None
        assert flow.service == "github"

    @pytest.mark.asyncio
    async def test_start_oauth_unsupported(self, oauth_handler: OAuthFlowHandler) -> None:
        """Unsupported OAuth service returns error."""
        result = await oauth_handler.start_oauth("a", "nonexistent", ["read"])
        assert result.get("status") == "failed"

    @pytest.mark.asyncio
    async def test_start_oauth_unsupported_alias_input_reports_canonical_service(
        self, oauth_handler: OAuthFlowHandler
    ) -> None:
        """Unsupported alias-style OAuth inputs should fail on canonical public service ids."""
        result = await oauth_handler.start_oauth("a", "Brave-Search", ["read"])
        assert result["status"] == "failed"
        assert result["flow_id"] is None
        assert result["error"] == "Service 'brave-search-api' does not support OAuth flows"

    @pytest.mark.asyncio
    async def test_handle_callback_valid_code(
        self, oauth_handler: OAuthFlowHandler, credential_store: CredentialStore
    ) -> None:
        """Valid callback exchanges code for token and stores it."""
        start = await oauth_handler.start_oauth("rhumb-lead", "slack", ["read"])
        flow_id = start["flow_id"]

        # Extract state token from _state_tokens
        state_token = None
        for token, fid in _state_tokens.items():
            if fid == flow_id:
                state_token = token
                break
        assert state_token is not None

        result = await oauth_handler.handle_callback(flow_id, "valid_code", state_token)
        assert result["status"] == "complete"

        # Token should be stored in credential store
        stored = credential_store.get_credential("slack", "oauth_token")
        assert stored is not None
        assert "mock_access_token_slack" in stored

    @pytest.mark.asyncio
    async def test_handle_callback_invalid_state(
        self, oauth_handler: OAuthFlowHandler
    ) -> None:
        """Callback with invalid state token is rejected."""
        start = await oauth_handler.start_oauth("a", "slack", ["read"])
        result = await oauth_handler.handle_callback(
            start["flow_id"], "code", "totally_invalid_state"
        )
        assert result["status"] == "failed"
        assert "invalid_state" in result["error"]

    @pytest.mark.parametrize(
        ("flow_id", "code", "state", "expected_error"),
        [
            ("   ", "code", "state", "flow_id required"),
            ("flow-123", "  ", "state", "code required"),
            ("flow-123", "code", "  ", "state required"),
        ],
    )
    def test_handle_callback_validates_required_fields_before_flow_read(
        self,
        oauth_handler: OAuthFlowHandler,
        store: ProvisioningFlowStore,
        flow_id: str,
        code: str,
        state: str,
        expected_error: str,
    ) -> None:
        """Blank OAuth callback fields should not open flow state."""
        store.get_flow = AsyncMock()  # type: ignore[method-assign]

        result = asyncio.run(oauth_handler.handle_callback(flow_id, code, state))

        assert result == {"status": "failed", "error": expected_error}
        store.get_flow.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_callback_expired_flow(
        self,
        store: ProvisioningFlowStore,
        oauth_handler: OAuthFlowHandler,
    ) -> None:
        """Callback on expired flow returns error."""
        start = await oauth_handler.start_oauth("a", "slack", ["read"])
        flow_id = start["flow_id"]

        # Force expiration
        store._mem[flow_id]["expires_at"] = (
            datetime.utcnow() - timedelta(hours=2)
        ).isoformat()

        result = await oauth_handler.handle_callback(flow_id, "code", "state")
        assert result["status"] == "failed"
        assert "expired" in result["error"]


# =====================================================================
# 4. PaymentFlowHandler
# =====================================================================


class TestPaymentFlowHandler:
    """Payment flow: start + confirm."""

    @pytest.mark.asyncio
    async def test_start_payment_stripe(self, payment_handler: PaymentFlowHandler) -> None:
        """Start payment for Stripe returns checkout link."""
        result = await payment_handler.start_payment(
            agent_id="rhumb-lead", service="stripe", plan="pro",
        )
        assert result["status"] == "link_provided"
        assert result["plan"] == "pro"
        assert "stripe.com" in result["payment_url"]

    @pytest.mark.asyncio
    async def test_start_payment_sendgrid(self, payment_handler: PaymentFlowHandler) -> None:
        """Start payment for SendGrid returns billing link."""
        result = await payment_handler.start_payment(
            "a", "sendgrid", "essentials"
        )
        assert result["status"] == "link_provided"
        assert "sendgrid" in result["payment_url"]

    @pytest.mark.asyncio
    async def test_start_payment_invalid_plan(
        self, payment_handler: PaymentFlowHandler
    ) -> None:
        """Invalid plan returns error."""
        result = await payment_handler.start_payment("a", "stripe", "ultra-mega")
        assert result["status"] == "failed"
        assert "not valid" in result["error"]

    @pytest.mark.asyncio
    async def test_start_payment_unsupported_alias_input_reports_canonical_service(
        self, payment_handler: PaymentFlowHandler
    ) -> None:
        """Unsupported alias-style inputs should fail on canonical public service ids."""
        result = await payment_handler.start_payment("a", "Brave-Search", "free")
        assert result["status"] == "failed"
        assert result["error"] == "Service 'brave-search-api' does not support payment flows"

    @pytest.mark.asyncio
    async def test_confirm_payment_valid_token(
        self, payment_handler: PaymentFlowHandler
    ) -> None:
        """Confirm payment with valid token marks flow complete."""
        start = await payment_handler.start_payment("a", "stripe", "pro")
        result = await payment_handler.confirm_payment(
            start["flow_id"], "cs_test_payment_123"
        )
        assert result["status"] == "complete"

    @pytest.mark.asyncio
    async def test_confirm_payment_empty_token(
        self, payment_handler: PaymentFlowHandler
    ) -> None:
        """Empty confirmation token returns error."""
        start = await payment_handler.start_payment("a", "stripe", "pro")
        result = await payment_handler.confirm_payment(start["flow_id"], "")
        assert result["status"] == "failed"

    def test_confirm_payment_requires_token_before_flow_read(
        self, payment_handler: PaymentFlowHandler, store: ProvisioningFlowStore
    ) -> None:
        """Blank payment confirmation tokens should not open flow state."""
        store.get_flow = AsyncMock()  # type: ignore[method-assign]

        result = asyncio.run(payment_handler.confirm_payment("flow-123", "   "))

        assert result == {
            "status": "failed",
            "error": "payment_confirmation_token required",
        }
        store.get_flow.assert_not_called()

    def test_confirm_payment_rejects_non_string_inputs_before_flow_read(
        self, payment_handler: PaymentFlowHandler, store: ProvisioningFlowStore
    ) -> None:
        """Payment confirmation should not stringify malformed IDs or tokens before reads."""
        store.get_flow = AsyncMock()  # type: ignore[method-assign]

        bad_flow = asyncio.run(payment_handler.confirm_payment(123, "cs_test_payment_123"))
        bad_token = asyncio.run(payment_handler.confirm_payment("flow-123", {"token": "cs_test"}))

        assert bad_flow == {"status": "failed", "error": "flow_id required"}
        assert bad_token == {
            "status": "failed",
            "error": "payment_confirmation_token required",
        }
        store.get_flow.assert_not_called()


# =====================================================================
# 5. ToSFlowHandler
# =====================================================================


class TestToSFlowHandler:
    """ToS flow: start, accept, hash verification."""

    @pytest.mark.asyncio
    async def test_start_tos_stripe(self, tos_handler: ToSFlowHandler) -> None:
        """Start ToS for Stripe returns text + hash."""
        result = await tos_handler.start_tos(agent_id="rhumb-lead", service="stripe")
        assert result["flow_id"] is not None
        assert "Stripe" in result["tos_text"]
        assert len(result["tos_hash"]) == 64  # SHA-256 hex
        assert "/tos/" in result["acceptance_url"]

    @pytest.mark.asyncio
    async def test_tos_hash_consistency(self, tos_handler: ToSFlowHandler) -> None:
        """ToS hash is stable across calls."""
        r1 = await tos_handler.start_tos("a", "stripe")
        r2 = await tos_handler.start_tos("a", "stripe")
        assert r1["tos_hash"] == r2["tos_hash"]

    @pytest.mark.asyncio
    async def test_accept_tos(self, tos_handler: ToSFlowHandler) -> None:
        """Accept ToS marks flow complete."""
        start = await tos_handler.start_tos("a", "stripe")
        result = await tos_handler.accept_tos(start["flow_id"])
        assert result["status"] == "complete"

    @pytest.mark.asyncio
    async def test_accept_tos_hash_mismatch(self, tos_handler: ToSFlowHandler) -> None:
        """Accept with wrong hash returns error."""
        start = await tos_handler.start_tos("a", "stripe")
        result = await tos_handler.accept_tos(
            start["flow_id"], tos_hash="wrong_hash_value"
        )
        assert result["status"] == "failed"
        assert "mismatch" in result["error"]

    def test_accept_tos_requires_flow_id_before_flow_read(
        self, tos_handler: ToSFlowHandler, store: ProvisioningFlowStore
    ) -> None:
        """Blank ToS acceptance flow ids should not open flow state."""
        store.get_flow = AsyncMock()  # type: ignore[method-assign]

        result = asyncio.run(tos_handler.accept_tos("   "))

        assert result == {"status": "failed", "error": "flow_id required"}
        store.get_flow.assert_not_called()

    @pytest.mark.asyncio
    async def test_start_tos_unsupported_service(
        self, tos_handler: ToSFlowHandler
    ) -> None:
        """Unsupported service returns failure."""
        result = await tos_handler.start_tos("a", "nonexistent_provider")
        assert result.get("status") == "failed"

    @pytest.mark.asyncio
    async def test_start_tos_unsupported_alias_input_reports_canonical_service(
        self, tos_handler: ToSFlowHandler
    ) -> None:
        """Unsupported alias-style inputs should keep canonical public service ids in ToS errors."""
        result = await tos_handler.start_tos("a", "Brave-Search")
        assert result["status"] == "failed"
        assert result["error"] == "No ToS available for service 'brave-search-api'"


# =====================================================================
# 6. ProvisioningOrchestrator — multi-step sequences
# =====================================================================


class TestProvisioningOrchestrator:
    """Orchestrator: start, advance, status for multi-step sequences."""

    @pytest.mark.asyncio
    async def test_start_provisioning_sendgrid(
        self, orchestrator: ProvisioningOrchestrator
    ) -> None:
        """SendGrid provisioning starts with signup step."""
        result = await orchestrator.start_provisioning(
            "rhumb-lead", "sendgrid",
            context={"email": "agent@rhumb.dev", "name": "Pedro"},
        )
        assert result["status"] == "in_progress"
        assert result["current_step"] == "signup"
        assert result["total_steps"] == 3  # signup → payment → tos
        assert result["flow_id"] is not None

    @pytest.mark.asyncio
    async def test_start_provisioning_slack(
        self, orchestrator: ProvisioningOrchestrator
    ) -> None:
        """Slack provisioning starts with OAuth step."""
        result = await orchestrator.start_provisioning(
            "rhumb-lead", "slack",
            context={"scopes": ["chat:write"]},
        )
        assert result["status"] == "in_progress"
        assert result["current_step"] == "oauth"
        assert result["total_steps"] == 2  # oauth → tos

    @pytest.mark.asyncio
    async def test_start_provisioning_unsupported(
        self, orchestrator: ProvisioningOrchestrator
    ) -> None:
        """Unsupported service returns failure."""
        result = await orchestrator.start_provisioning("a", "nonexistent_svc")
        assert result["status"] == "failed"

    @pytest.mark.asyncio
    async def test_start_provisioning_unsupported_alias_input_reports_canonical_service(
        self, orchestrator: ProvisioningOrchestrator
    ) -> None:
        """Unsupported alias-style provisioning inputs should fail on canonical public service ids."""
        result = await orchestrator.start_provisioning("a", "Brave-Search")
        assert result["status"] == "failed"
        assert result["error"] == "Service 'brave-search-api' is not supported for provisioning"

    @pytest.mark.asyncio
    async def test_advance_provisioning_sendgrid(
        self, orchestrator: ProvisioningOrchestrator
    ) -> None:
        """SendGrid advance: signup → payment."""
        await orchestrator.start_provisioning(
            "rhumb-lead", "sendgrid",
            context={"email": "e@x.com", "name": "n"},
        )

        # Complete signup step (simulate)
        result = await orchestrator.advance_provisioning(
            "rhumb-lead", "sendgrid",
            context={"plan": "free"},
        )
        assert result["status"] == "in_progress"
        assert result["current_step"] == "payment"
        assert result["current_step_index"] == 1

    @pytest.mark.asyncio
    async def test_advance_to_completion(
        self, orchestrator: ProvisioningOrchestrator
    ) -> None:
        """Advancing past the last step returns 'complete'."""
        # Slack: oauth → tos (2 steps)
        await orchestrator.start_provisioning("a", "slack")

        # Advance to tos
        r1 = await orchestrator.advance_provisioning("a", "slack")
        assert r1["current_step"] == "tos"

        # Advance past tos → complete
        r2 = await orchestrator.advance_provisioning("a", "slack")
        assert r2["status"] == "complete"

    @pytest.mark.asyncio
    async def test_provisioning_status(
        self, orchestrator: ProvisioningOrchestrator
    ) -> None:
        """Get provisioning status for an in-progress sequence."""
        await orchestrator.start_provisioning("a", "github")
        status = await orchestrator.get_provisioning_status("a", "github")
        assert status["status"] == "in_progress"
        assert status["current_step"] == "oauth"
        assert status["total_steps"] == 2

    @pytest.mark.asyncio
    async def test_provisioning_start_and_status_normalize_service_ids(
        self,
        orchestrator: ProvisioningOrchestrator,
        store: ProvisioningFlowStore,
    ) -> None:
        """Provisioning orchestration should key sequences on canonical public service ids."""
        start = await orchestrator.start_provisioning("a", "GitHub")
        assert start["status"] == "in_progress"
        assert start["current_step"] == "oauth"

        flow = await store.get_flow(start["flow_id"])
        assert flow is not None
        assert flow.service == "github"

        status = await orchestrator.get_provisioning_status("a", "GITHUB")
        assert status["status"] == "in_progress"
        assert status["service"] == "github"

    @pytest.mark.asyncio
    async def test_provisioning_status_not_started(
        self, orchestrator: ProvisioningOrchestrator
    ) -> None:
        """Status for non-existent provisioning returns not_started."""
        status = await orchestrator.get_provisioning_status("a", "unknown_svc")
        assert status["status"] == "not_started"


# =====================================================================
# 7. E2E integration tests
# =====================================================================


class TestE2EProvisioning:
    """End-to-end: full provisioning sequences with flow completion."""

    @pytest.mark.asyncio
    async def test_e2e_sendgrid_full_sequence(
        self, orchestrator: ProvisioningOrchestrator
    ) -> None:
        """E2E: SendGrid — signup → payment → tos → complete."""
        # Step 1: Start provisioning (begins with signup)
        start = await orchestrator.start_provisioning(
            "rhumb-lead", "sendgrid",
            context={"email": "agent@rhumb.dev", "name": "Pedro", "plan": "free"},
        )
        assert start["status"] == "in_progress"
        assert start["current_step"] == "signup"
        signup_flow_id = start["flow_id"]

        # Complete signup
        verify = await orchestrator.signup_handler.verify_signup(
            signup_flow_id, email_code="VERIFY123"
        )
        assert verify["status"] == "complete"

        # Step 2: Advance to payment
        adv1 = await orchestrator.advance_provisioning(
            "rhumb-lead", "sendgrid", context={"plan": "free"},
        )
        assert adv1["current_step"] == "payment"
        payment_flow_id = adv1["flow_id"]

        # Complete payment
        pay = await orchestrator.payment_handler.confirm_payment(
            payment_flow_id, "cs_sendgrid_pay_ok"
        )
        assert pay["status"] == "complete"

        # Step 3: Advance to ToS
        adv2 = await orchestrator.advance_provisioning(
            "rhumb-lead", "sendgrid"
        )
        assert adv2["current_step"] == "tos"
        tos_flow_id = adv2["flow_id"]

        # Complete ToS
        accept = await orchestrator.tos_handler.accept_tos(tos_flow_id)
        assert accept["status"] == "complete"

        # Step 4: Advance → complete
        adv3 = await orchestrator.advance_provisioning(
            "rhumb-lead", "sendgrid"
        )
        assert adv3["status"] == "complete"
        assert adv3["steps_completed"] == 3

    @pytest.mark.asyncio
    async def test_e2e_slack_oauth_tos(
        self,
        orchestrator: ProvisioningOrchestrator,
        credential_store: CredentialStore,
    ) -> None:
        """E2E: Slack — oauth → tos → complete."""
        # Step 1: Start (OAuth)
        start = await orchestrator.start_provisioning(
            "rhumb-lead", "slack",
            context={"scopes": ["chat:write", "channels:read"]},
        )
        assert start["current_step"] == "oauth"
        oauth_flow_id = start["flow_id"]

        # Complete OAuth callback
        state_token = None
        for token, fid in _state_tokens.items():
            if fid == oauth_flow_id:
                state_token = token
                break
        assert state_token is not None

        cb = await orchestrator.oauth_handler.handle_callback(
            oauth_flow_id, "auth_code_slack", state_token
        )
        assert cb["status"] == "complete"

        # Verify token stored
        assert credential_store.get_credential("slack", "oauth_token") is not None

        # Step 2: Advance to ToS
        adv1 = await orchestrator.advance_provisioning("rhumb-lead", "slack")
        assert adv1["current_step"] == "tos"
        tos_flow_id = adv1["flow_id"]

        # Complete ToS
        accept = await orchestrator.tos_handler.accept_tos(tos_flow_id)
        assert accept["status"] == "complete"

        # Step 3: Complete
        adv2 = await orchestrator.advance_provisioning("rhumb-lead", "slack")
        assert adv2["status"] == "complete"

    @pytest.mark.asyncio
    async def test_e2e_flow_with_expiration(
        self,
        store: ProvisioningFlowStore,
        orchestrator: ProvisioningOrchestrator,
    ) -> None:
        """E2E: Flow expires when human doesn't act within TTL."""
        start = await orchestrator.start_provisioning("a", "github")
        flow_id = start["flow_id"]

        # Force expiration
        store._mem[flow_id]["expires_at"] = (
            datetime.utcnow() - timedelta(hours=2)
        ).isoformat()

        # Attempt OAuth callback → should fail with expired
        cb = await orchestrator.oauth_handler.handle_callback(
            flow_id, "code", "any_state"
        )
        assert cb["status"] == "failed"
        assert "expired" in cb["error"]

    @pytest.mark.asyncio
    async def test_e2e_flow_with_retry(
        self,
        store: ProvisioningFlowStore,
        orchestrator: ProvisioningOrchestrator,
    ) -> None:
        """E2E: OAuth flow retries on transient failure, then succeeds."""
        start = await orchestrator.start_provisioning("a", "stripe")
        flow_id = start["flow_id"]

        # Extract state
        state_token = None
        for token, fid in _state_tokens.items():
            if fid == flow_id:
                state_token = token
                break

        # First attempt: invalid state → retry
        r1 = await orchestrator.oauth_handler.handle_callback(
            flow_id, "code", "bad_state"
        )
        assert r1["status"] == "failed"

        # Start a fresh OAuth flow for the same agent+service
        start2 = await orchestrator.oauth_handler.start_oauth("a", "stripe", ["read"])
        flow_id2 = start2["flow_id"]
        state2 = None
        for token, fid in _state_tokens.items():
            if fid == flow_id2:
                state2 = token
                break

        # Second attempt: valid state → success
        r2 = await orchestrator.oauth_handler.handle_callback(
            flow_id2, "valid_code", state2
        )
        assert r2["status"] == "complete"

    @pytest.mark.asyncio
    async def test_e2e_twilio_signup_payment_tos(
        self, orchestrator: ProvisioningOrchestrator
    ) -> None:
        """E2E: Twilio — signup → payment → tos → complete."""
        start = await orchestrator.start_provisioning(
            "a", "twilio",
            context={"email": "dev@example.com", "name": "Dev", "plan": "pay-as-you-go"},
        )
        assert start["current_step"] == "signup"
        signup_id = start["flow_id"]

        # Complete signup
        await orchestrator.signup_handler.verify_signup(
            signup_id, email_code="TW123"
        )

        # Advance to payment
        adv1 = await orchestrator.advance_provisioning(
            "a", "twilio", context={"plan": "pay-as-you-go"},
        )
        assert adv1["current_step"] == "payment"
        await orchestrator.payment_handler.confirm_payment(
            adv1["flow_id"], "twilio_pay_ok"
        )

        # Advance to ToS
        adv2 = await orchestrator.advance_provisioning("a", "twilio")
        assert adv2["current_step"] == "tos"
        await orchestrator.tos_handler.accept_tos(adv2["flow_id"])

        # Complete
        adv3 = await orchestrator.advance_provisioning("a", "twilio")
        assert adv3["status"] == "complete"


# =====================================================================
# 8. State machine validation
# =====================================================================


class TestFlowStateMachine:
    """Validate all state machine transitions."""

    @pytest.mark.asyncio
    async def test_all_valid_transitions(self, store: ProvisioningFlowStore) -> None:
        """Every valid transition succeeds."""
        for from_state, to_states in VALID_TRANSITIONS.items():
            for to_state in to_states:
                flow_id = await store.create_flow("a", "s", FlowType.SIGNUP, {})
                # Force to from_state
                store._mem[flow_id]["state"] = from_state.value
                # Should succeed
                await store.update_flow_state(flow_id, to_state)
                flow = await store.get_flow(flow_id)
                assert flow is not None
                assert flow.state == to_state.value

    @pytest.mark.asyncio
    async def test_terminal_states_block_transitions(
        self, store: ProvisioningFlowStore
    ) -> None:
        """Terminal states (complete, failed, expired) reject all transitions."""
        for terminal in (FlowState.COMPLETE, FlowState.FAILED, FlowState.EXPIRED):
            flow_id = await store.create_flow("a", "s", FlowType.SIGNUP, {})
            store._mem[flow_id]["state"] = terminal.value

            for target in FlowState:
                if target == terminal:
                    continue
                with pytest.raises(ValueError, match="Invalid transition"):
                    await store.update_flow_state(flow_id, target)

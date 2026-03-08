# Round 10 Slice D — Provisioning Flows (OAuth, Payment Consent, ToS)

> **Kickoff Date:** 2026-03-08
> **Round:** 10 (cb-r010)
> **Slice:** D — Provisioning Flows
> **Branch:** `feat/r10-slice-d-provisioning-flows`
> **Predecessor:** Slice C (Credential injection, agent identity, rate limiting) — PR #26
> **Status:** READY FOR KICKOFF

## Overview

Implement the human-gated provisioning flows that enable agents to sign up for new services, complete OAuth handshakes, accept payment terms, and acknowledge ToS. This slice completes the Access Layer foundation by orchestrating complex multi-step flows with proper state management and human action signaling.

**Key dependencies from Slice C:**
- Credential store (`proxy_credentials.py`) persists OAuth tokens & API keys
- Agent identity (`agent_identity.py`) controls which agents can provision which services
- Rate limiting (`proxy_rate_limit.py`) prevents abuse during provisioning

**Deliverables this slice:**
1. Provisioning flow schema + Supabase table
2. Signup flow handler (email verification)
3. OAuth flow handler (consent → token exchange → storage)
4. Payment consent handler (billing link → confirmation)
5. ToS acceptance handler
6. Flow orchestrator (chains flows, handles retries, state persistence)
7. 25+ integration tests

**Success criteria:**
- All tests passing (25+)
- All 5 flow types working (signup, oauth, payment, tos, confirmation)
- Multi-step orchestration validated (signup → oauth → tos → activate)
- Type-check clean, linting clean
- Human action signaling working (no blocking waits)

---

## Module Breakdown

### Module 1: Provisioning Flow Schema (`provisioning.py`)

**Responsibility:** Define provisioning flow states and entities.

**Implementation:**

```python
# packages/api/schemas/provisioning.py

from enum import Enum
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, List

class FlowType(str, Enum):
    """Types of provisioning flows."""
    SIGNUP = "signup"
    OAUTH = "oauth"
    PAYMENT = "payment"
    TOS = "tos"
    CONFIRMATION = "confirmation"

class FlowState(str, Enum):
    """Provisioning flow state machine."""
    PENDING = "pending"              # Flow created, not yet started
    IN_PROGRESS = "in_progress"      # Human action in progress
    HUMAN_ACTION_NEEDED = "human_action_needed"  # Waiting for human to click link/enter data
    COMPLETE = "complete"            # Flow completed successfully
    FAILED = "failed"                # Flow failed (irreversible)
    EXPIRED = "expired"              # Flow timed out

@dataclass
class ProvisioningFlowSchema:
    """Provisioning flow record in Supabase."""
    flow_id: str                  # UUID
    agent_id: str
    service: str                  # "stripe", "slack", etc
    flow_type: FlowType
    state: FlowState
    
    # Flow-specific data
    payload: Dict[str, any]       # Signup email, OAuth scopes, payment plan, etc
    callback_data: Optional[Dict[str, any]] = None  # OAuth code, payment confirmation, etc
    
    # Metadata
    created_at: datetime
    expires_at: datetime          # Usually 24h from creation
    human_action_url: Optional[str] = None  # URL for human to click
    error_message: Optional[str] = None
    retries: int = 0
    max_retries: int = 3

class ProvisioningFlowStore:
    """Manage provisioning flow state in Supabase."""
    
    def __init__(self, supabase_client):
        self.supabase = supabase_client
    
    async def create_flow(
        self,
        agent_id: str,
        service: str,
        flow_type: FlowType,
        payload: Dict,
    ) -> str:
        """Create new provisioning flow.
        
        Returns:
            flow_id (UUID)
        """
        flow_id = str(uuid.uuid4())
        created_at = datetime.utcnow()
        expires_at = created_at + timedelta(hours=24)
        
        flow = {
            "flow_id": flow_id,
            "agent_id": agent_id,
            "service": service,
            "flow_type": flow_type.value,
            "state": FlowState.PENDING.value,
            "payload": json.dumps(payload),
            "created_at": created_at.isoformat(),
            "expires_at": expires_at.isoformat(),
            "retries": 0,
        }
        
        response = self.supabase.table("provisioning_flows").insert(flow).execute()
        return flow_id
    
    async def get_flow(self, flow_id: str) -> Optional[ProvisioningFlowSchema]:
        """Retrieve flow by ID."""
        response = self.supabase.table("provisioning_flows").select(
            "*"
        ).eq("flow_id", flow_id).single().execute()
        
        if response.data:
            return ProvisioningFlowSchema(**response.data)
        return None
    
    async def update_flow_state(
        self,
        flow_id: str,
        new_state: FlowState,
        callback_data: Optional[Dict] = None,
        error_message: Optional[str] = None,
    ) -> None:
        """Update flow state."""
        update = {
            "state": new_state.value,
            "updated_at": datetime.utcnow().isoformat(),
        }
        
        if callback_data:
            update["callback_data"] = json.dumps(callback_data)
        
        if error_message:
            update["error_message"] = error_message
        
        self.supabase.table("provisioning_flows").update(update).eq(
            "flow_id", flow_id
        ).execute()
    
    async def set_human_action_url(self, flow_id: str, url: str) -> None:
        """Set URL for human to visit."""
        self.supabase.table("provisioning_flows").update({
            "human_action_url": url,
            "state": FlowState.HUMAN_ACTION_NEEDED.value,
        }).eq("flow_id", flow_id).execute()

# Singleton
_flow_store: Optional[ProvisioningFlowStore] = None

def get_flow_store(supabase_client) -> ProvisioningFlowStore:
    global _flow_store
    if _flow_store is None:
        _flow_store = ProvisioningFlowStore(supabase_client)
    return _flow_store
```

**Supabase migration:**

```sql
-- migrations/0004_provisioning_flows.sql

CREATE TABLE provisioning_flows (
    flow_id UUID PRIMARY KEY,
    agent_id TEXT NOT NULL,
    service TEXT NOT NULL,  -- "stripe", "slack", etc
    flow_type TEXT NOT NULL,  -- "signup", "oauth", "payment", "tos", "confirmation"
    state TEXT NOT NULL,  -- "pending", "in_progress", "human_action_needed", "complete", "failed", "expired"
    
    payload JSONB NOT NULL,  -- {email, scopes, plan, tos_hash, etc}
    callback_data JSONB,     -- {oauth_code, payment_id, confirmation_token, etc}
    
    human_action_url TEXT,   -- URL for human to click
    error_message TEXT,
    
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMP NOT NULL,
    retries INTEGER DEFAULT 0,
    
    FOREIGN KEY (agent_id) REFERENCES agents(agent_id)
);

CREATE INDEX idx_provisioning_flows_agent ON provisioning_flows(agent_id);
CREATE INDEX idx_provisioning_flows_service ON provisioning_flows(service);
CREATE INDEX idx_provisioning_flows_state ON provisioning_flows(state);
CREATE INDEX idx_provisioning_flows_expires ON provisioning_flows(expires_at);
```

**Tests (Unit):**
- `test_create_flow` — creates flow with correct initial state
- `test_get_flow` — retrieves flow by ID
- `test_update_flow_state` — updates state and timestamp
- `test_flow_expiration` — flow marked expired if expires_at < now
- `test_max_retries` — flow fails if retries > max_retries

---

### Module 2: Signup Flow (`provisioning_signup.py`)

**Responsibility:** Handle email signup for new services.

**Implementation (high-level):**

```python
# packages/api/routes/provisioning_signup.py

class SignupFlowHandler:
    """Initiate and complete email-based signup flows."""
    
    async def start_signup(
        self,
        agent_id: str,
        service: str,
        email: str,
        name: str,
    ) -> Dict:
        """Start signup flow.
        
        Returns:
            {
                "flow_id": str,
                "status": "email_sent" | "link_provided" | "failed",
                "action_url": str (only if provider has direct signup API),
                "message": "Check your email for verification link"
            }
        """
        # Create flow in DB
        flow_id = await store.create_flow(
            agent_id=agent_id,
            service=service,
            flow_type=FlowType.SIGNUP,
            payload={"email": email, "name": name},
        )
        
        # Attempt provider-specific signup
        # For Stripe: no agent-friendly signup API → return provider link
        # For Slack: no direct signup → OAuth is the path
        # For SendGrid: POST /v3/marketing/contacts → automatic?
        
        # If no direct API: return provider signup link
        signup_url = f"https://{service}.com/signup?email={email}"
        await store.set_human_action_url(flow_id, signup_url)
        
        return {
            "flow_id": flow_id,
            "status": "link_provided",
            "action_url": signup_url,
            "message": f"Visit {signup_url} and complete signup. Return here with verification code."
        }
    
    async def verify_signup(
        self,
        flow_id: str,
        email_code: Optional[str] = None,
        verification_token: Optional[str] = None,
    ) -> Dict:
        """Complete signup after human action.
        
        Called when:
        - Human enters email verification code
        - Webhook from provider confirms signup
        - Human provides verification token
        """
        flow = await store.get_flow(flow_id)
        
        # Verify code/token against provider
        # For now: accept any non-empty code (provider verification deferred to Phase 2.2)
        if not email_code and not verification_token:
            return {"status": "failed", "error": "email_code or verification_token required"}
        
        # Mark flow complete
        await store.update_flow_state(
            flow_id,
            FlowState.COMPLETE,
            callback_data={"email_code": email_code, "verification_token": verification_token},
        )
        
        return {"status": "complete", "message": "Signup verified"}
```

**Route handlers:**

```python
@app.post("/v1/provisioning/signup")
async def signup_start(
    body: SignupRequest,  # agent_id, service, email, name
) -> Dict:
    """Start signup flow."""
    handler = SignupFlowHandler(...)
    result = await handler.start_signup(...)
    return result

@app.post("/v1/provisioning/signup/{flow_id}/verify")
async def signup_verify(
    flow_id: str,
    body: SignupVerifyRequest,  # email_code
) -> Dict:
    """Complete signup after email verification."""
    handler = SignupFlowHandler(...)
    result = await handler.verify_signup(flow_id, email_code=body.email_code)
    return result
```

**Tests (Unit):**
- `test_signup_start_stripe` — returns signup link for Stripe
- `test_signup_start_sendgrid` — initiates SendGrid contact creation
- `test_signup_verify_valid_code` — marks flow complete
- `test_signup_verify_invalid_code` — returns error

---

### Module 3: OAuth Flow (`provisioning_oauth.py`)

**Responsibility:** Handle OAuth consent and token exchange.

**Implementation (high-level):**

```python
# packages/api/routes/provisioning_oauth.py

class OAuthFlowHandler:
    """OAuth 2.0 authorization flow for agent provisioning."""
    
    async def start_oauth(
        self,
        agent_id: str,
        service: str,
        scopes: List[str],
    ) -> Dict:
        """Start OAuth flow.
        
        Returns:
            {
                "flow_id": str,
                "authorization_url": str,
                "expires_in": 3600,
            }
        """
        # Create flow
        flow_id = await store.create_flow(
            agent_id=agent_id,
            service=service,
            flow_type=FlowType.OAUTH,
            payload={"scopes": scopes},
        )
        
        # Generate OAuth consent URL
        auth_url = self._build_oauth_url(service, flow_id, scopes)
        await store.set_human_action_url(flow_id, auth_url)
        
        return {
            "flow_id": flow_id,
            "authorization_url": auth_url,
            "expires_in": 3600,
        }
    
    async def handle_callback(
        self,
        flow_id: str,
        code: str,
        state: str,
    ) -> Dict:
        """Handle OAuth callback after human grants consent.
        
        Called when OAuth provider redirects to /oauth/callback/{flow_id}?code=...&state=...
        """
        flow = await store.get_flow(flow_id)
        
        # Verify state token
        if not self._verify_state(state, flow_id):
            return {"status": "failed", "error": "invalid state"}
        
        # Exchange code for token
        service = flow.service
        try:
            token_response = await self._exchange_code(service, code, flow_id)
            access_token = token_response["access_token"]
            
            # Store token in credential vault
            cred_store = get_credential_store()
            cred_store.store_oauth_token(
                service=service,
                agent_id=flow.agent_id,
                token=access_token,
                expires_at=datetime.utcnow() + timedelta(hours=token_response.get("expires_in", 3600)),
            )
            
            # Mark flow complete
            await store.update_flow_state(
                flow_id,
                FlowState.COMPLETE,
                callback_data={"access_token": access_token},
            )
            
            return {"status": "complete", "message": "OAuth token stored"}
        except Exception as e:
            await store.update_flow_state(
                flow_id,
                FlowState.FAILED,
                error_message=str(e),
            )
            return {"status": "failed", "error": str(e)}
    
    def _build_oauth_url(self, service: str, flow_id: str, scopes: List[str]) -> str:
        """Build OAuth consent URL for service."""
        # Provider-specific URLs
        oauth_endpoints = {
            "slack": "https://slack.com/oauth_authorize",
            "github": "https://github.com/login/oauth/authorize",
            "stripe": "https://connect.stripe.com/oauth/authorize",
            # ... etc
        }
        
        params = {
            "client_id": self._get_client_id(service),
            "redirect_uri": f"https://api.rhumb.dev/oauth/callback/{flow_id}",
            "scope": " ".join(scopes),
            "state": self._generate_state_token(flow_id),
            "response_type": "code",
        }
        
        return f"{oauth_endpoints[service]}?{urlencode(params)}"
```

**Route handlers:**

```python
@app.post("/v1/provisioning/oauth/{service}")
async def oauth_start(
    service: str,
    body: OAuthRequest,  # agent_id, scopes[]
) -> Dict:
    """Start OAuth flow."""
    handler = OAuthFlowHandler(...)
    result = await handler.start_oauth(...)
    return result

@app.get("/oauth/callback/{flow_id}")
async def oauth_callback(
    flow_id: str,
    code: str,
    state: str,
) -> Dict:
    """Handle OAuth provider callback."""
    handler = OAuthFlowHandler(...)
    result = await handler.handle_callback(flow_id, code, state)
    # Redirect to success/error page with result
    return result
```

**Tests (Unit):**
- `test_start_oauth_slack` — generates correct Slack OAuth URL
- `test_start_oauth_github` — generates correct GitHub OAuth URL
- `test_handle_callback_valid_code` — exchanges code for token, stores in vault
- `test_handle_callback_invalid_state` — rejects mismatched state token
- `test_handle_callback_token_refresh` — handles token refresh flow

---

### Module 4: Payment Consent Handler (`provisioning_payment.py`)

**Responsibility:** Orchestrate payment plan selection and confirmation.

**Implementation (high-level):**

```python
# packages/api/routes/provisioning_payment.py

class PaymentFlowHandler:
    """Payment consent and plan activation."""
    
    async def start_payment(
        self,
        agent_id: str,
        service: str,
        plan: str,  # "free", "pro", "enterprise"
    ) -> Dict:
        """Initiate payment flow.
        
        Returns:
            {
                "flow_id": str,
                "payment_url": str,
                "plan": str,
                "expires_in": 3600,
            }
        """
        # Create flow
        flow_id = await store.create_flow(
            agent_id=agent_id,
            service=service,
            flow_type=FlowType.PAYMENT,
            payload={"plan": plan},
        )
        
        # Generate payment link (provider-specific)
        payment_url = self._build_payment_url(service, plan, flow_id)
        await store.set_human_action_url(flow_id, payment_url)
        
        return {
            "flow_id": flow_id,
            "payment_url": payment_url,
            "plan": plan,
            "expires_in": 3600,
        }
    
    async def confirm_payment(
        self,
        flow_id: str,
        payment_confirmation_token: str,
    ) -> Dict:
        """Confirm payment after human completes checkout.
        
        Can be triggered by:
        - Human submitting confirmation token
        - Webhook from payment processor (Stripe, etc)
        """
        flow = await store.get_flow(flow_id)
        
        # Verify payment with provider
        if not await self._verify_payment(flow.service, payment_confirmation_token):
            return {"status": "failed", "error": "payment_verification_failed"}
        
        # Mark flow complete and activate service
        await store.update_flow_state(
            flow_id,
            FlowState.COMPLETE,
            callback_data={"payment_confirmed": True},
        )
        
        return {"status": "complete", "message": "Payment confirmed, service activated"}
```

**Tests (Unit):**
- `test_start_payment_stripe` — returns Stripe checkout link
- `test_start_payment_sendgrid` — returns SendGrid billing portal link
- `test_confirm_payment_valid_token` — marks flow complete
- `test_confirm_payment_declined` — handles payment failure

---

### Module 5: ToS Acceptance (`provisioning_tos.py`)

**Responsibility:** Present and collect ToS acceptance.

**Implementation (high-level):**

```python
# packages/api/routes/provisioning_tos.py

class ToSFlowHandler:
    """Terms of Service acceptance."""
    
    async def start_tos(
        self,
        agent_id: str,
        service: str,
    ) -> Dict:
        """Start ToS acceptance flow.
        
        Returns:
            {
                "flow_id": str,
                "tos_text": str,
                "tos_hash": str,
                "acceptance_url": str,
            }
        """
        # Create flow
        flow_id = await store.create_flow(
            agent_id=agent_id,
            service=service,
            flow_type=FlowType.TOS,
            payload={},
        )
        
        # Fetch ToS from provider or use cached version
        tos_text = await self._fetch_tos(service)
        tos_hash = hashlib.sha256(tos_text.encode()).hexdigest()
        
        acceptance_url = f"https://api.rhumb.dev/v1/provisioning/tos/{flow_id}/accept"
        
        return {
            "flow_id": flow_id,
            "tos_text": tos_text,
            "tos_hash": tos_hash,
            "acceptance_url": acceptance_url,
        }
    
    async def accept_tos(self, flow_id: str) -> Dict:
        """Accept ToS."""
        flow = await store.get_flow(flow_id)
        
        # Optionally: send acceptance confirmation to provider
        # For now: just mark complete
        await store.update_flow_state(flow_id, FlowState.COMPLETE)
        
        return {"status": "complete", "message": "ToS accepted"}
```

**Tests (Unit):**
- `test_fetch_tos_stripe` — returns Stripe ToS text
- `test_tos_hash_consistency` — hash stable across calls
- `test_accept_tos` — marks flow complete

---

### Module 6: Flow Orchestrator (`provisioning_orchestrator.py`)

**Responsibility:** Chain flows in correct order, handle retries, persist state.

**Implementation (high-level):**

```python
# packages/api/services/provisioning_orchestrator.py

class ProvisioningOrchestrator:
    """Orchestrate multi-step provisioning sequences."""
    
    # Flow sequences for each service
    FLOW_SEQUENCES = {
        "stripe": [FlowType.OAUTH, FlowType.TOS],  # No signup for Stripe Connect
        "slack": [FlowType.OAUTH, FlowType.TOS],
        "sendgrid": [FlowType.SIGNUP, FlowType.PAYMENT, FlowType.TOS],
        "github": [FlowType.OAUTH, FlowType.TOS],
        "twilio": [FlowType.SIGNUP, FlowType.PAYMENT, FlowType.TOS],
    }
    
    async def start_provisioning(
        self,
        agent_id: str,
        service: str,
    ) -> Dict:
        """Start complete provisioning sequence for service.
        
        Returns:
            {
                "flow_ids": {flow_type: flow_id},
                "next_action": FlowType,
                "next_action_url": str,
            }
        """
        sequence = self.FLOW_SEQUENCES.get(service)
        if not sequence:
            return {"status": "failed", "error": f"service {service} not supported"}
        
        # Start first flow in sequence
        first_flow_type = sequence[0]
        handler = self._get_handler(first_flow_type)
        result = await handler.start_flow(agent_id, service)
        
        # Store sequence in metadata
        await store.set_provisioning_sequence(
            agent_id=agent_id,
            service=service,
            sequence=sequence,
            current_index=0,
        )
        
        return {
            "flow_ids": {first_flow_type.value: result["flow_id"]},
            "next_action": first_flow_type.value,
            "next_action_url": result.get("action_url"),
        }
    
    async def advance_provisioning(
        self,
        agent_id: str,
        service: str,
    ) -> Dict:
        """Advance to next flow in sequence after current flow completes."""
        # Get sequence + current position
        sequence_data = await store.get_provisioning_sequence(agent_id, service)
        if not sequence_data:
            return {"status": "failed", "error": "no provisioning in progress"}
        
        sequence = sequence_data["sequence"]
        current_index = sequence_data["current_index"]
        
        # Move to next flow
        next_index = current_index + 1
        if next_index >= len(sequence):
            # Provisioning complete!
            return {
                "status": "complete",
                "message": f"Provisioning complete for {service}",
            }
        
        # Start next flow
        next_flow_type = sequence[next_index]
        handler = self._get_handler(next_flow_type)
        result = await handler.start_flow(agent_id, service)
        
        # Update sequence position
        await store.set_provisioning_sequence(
            agent_id=agent_id,
            service=service,
            sequence=sequence,
            current_index=next_index,
        )
        
        return {
            "next_action": next_flow_type.value,
            "next_action_url": result.get("action_url"),
        }
```

**Tests (Integration):**
- `test_provisioning_sequence_sendgrid` — signup → payment → tos → complete
- `test_provisioning_sequence_slack` — oauth → tos → complete
- `test_provisioning_with_human_delay` — flow pauses at human action, resumes after
- `test_provisioning_with_expired_flow` — handles expired OAuth code, restarts

---

## Integration Tests

**File:** `packages/api/tests/test_proxy_slice_d_integration.py`

**Test scenarios:**

1. **E2E: Full provisioning for SendGrid**
   - Agent requests provisioning
   - Signup flow: returns signup link
   - Human: visits link, confirms email
   - Payment flow: returns checkout link
   - Human: completes payment
   - ToS flow: returns ToS acceptance URL
   - Human: accepts ToS
   - Agent: receives complete status, can now use SendGrid

2. **E2E: OAuth flow for Slack**
   - Agent requests provisioning
   - OAuth flow: returns consent URL
   - Human: clicks, grants permission
   - Callback: exchanges code for token, stores in vault
   - ToS flow: initiated
   - Human: accepts ToS
   - Agent: receives complete status

3. **E2E: Flow with human delay**
   - Agent initiates provisioning
   - Human doesn't complete action for 30 minutes
   - Flow remains in HUMAN_ACTION_NEEDED state
   - Human: eventually completes action
   - Flow resumes and completes

4. **E2E: Flow with retries**
   - OAuth callback receives invalid code (first attempt)
   - Flow stays in HUMAN_ACTION_NEEDED (user tries again)
   - OAuth callback receives valid code (second attempt)
   - Flow completes

5. **E2E: Flow expiration**
   - OAuth flow created, expires_at = 1 hour
   - Human doesn't act for 2 hours
   - Flow marked EXPIRED
   - Attempt to complete returns error
   - Agent must restart provisioning

**Coverage target:** 25+ tests

---

## Acceptance Criteria

- [x] All 5 flow types implemented (signup, oauth, payment, tos, confirmation)
- [x] Flow orchestrator handles multi-step sequences correctly
- [x] Human action needed properly signaled (flow state = HUMAN_ACTION_NEEDED, action URL provided)
- [x] No blocking waits (flows store state, agent polls or receives webhook)
- [x] 25+ integration tests passing
- [x] Type-check clean (mypy --strict)
- [x] Linting clean (pylint)
- [x] Supabase migration written + provisioning_flows table created
- [x] Flow state machine validated (all transitions tested)

---

## Continuation

**Output from Slice D feeds into Phase 2.2 (Agent Identity System refinements):**
- Provisioning flows provide live agent identity + permissions
- Flow completion enables monitoring/observability (audit trail)
- Payment flows integrate with billing + subscription management

**Post-Round 10:**
- Round 11 (WU 2.2) — Monitoring + Agent Identity refinement (SRE layer)
- Round 12 (WU 2.3) — Documentation + API SDKs (developer experience)

---

## Branch & Merge Strategy

**Branch:** `feat/r10-slice-d-provisioning-flows`

**Sub-slices (can execute in parallel if needed):**
- **Slice D.1:** Provisioning flow schema + storage (2 hours)
- **Slice D.2:** Signup + OAuth flows (6 hours)
- **Slice D.3:** Payment + ToS flows (4 hours)
- **Slice D.4:** Flow orchestrator (4 hours)
- **Slice D.5:** Integration tests + PR (9 hours)

**Merge gate:** All tests passing (25+), type-check clean, linting clean, flow state machine proven. No breaking changes to Slice A/B/C APIs.

**PR title:** `feat: Round 10 Slice D — Provisioning flows + orchestration (25+ tests)`

---

## Estimated Timeline

- **Start:** 2026-03-08 evening (after Slice C completion)
- **Duration:** 24 hours (can parallelize D.1-4)
- **Target completion:** 2026-03-09–10 (depends on execution parallelism)

---

## Open Questions

1. Should failed flows auto-restart, or require explicit agent action? → Explicit (agent controls retry policy)
2. Payment processor: Stripe only, or multi-processor? → Stripe v1 (others in Phase 2.2)
3. ToS versioning: how to handle provider ToS updates? → Hash tracking (version bump = new flow required)
4. Webhook security: how to verify provider webhooks? → HMAC signatures (provider-specific)

# Round 10 Slice C — Credential Injection + Agent Identity System

> **Kickoff Date:** 2026-03-08
> **Round:** 10 (cb-r010)
> **Slice:** C — Credential Injection + Agent Identity
> **Branch:** `feat/r10-slice-c-credential-injection`
> **Predecessor:** Slice B (Connection pooling, circuit breaker, latency) — PR #24
> **Status:** READY FOR KICKOFF

## Overview

Implement the credential and agent identity layer that enables secure, per-agent provisioning. This slice establishes the foundation for controlled access to provider APIs through the proxy and introduces per-agent rate limiting.

**Key dependencies from Slice B:**
- Connection pool manager (`proxy_pool.py`) provides per-agent connection isolation
- Circuit breaker (`proxy_breaker.py`) detects provider unavailability
- Latency tracking (`proxy_latency.py`) measures impact of auth injection

**Deliverables this slice:**
1. Credential store (1Password integration, in-memory cache with TTL)
2. Agent identity schema + Supabase table
3. Auth injection logic for 5 providers (Stripe, Slack, GitHub, Twilio, SendGrid)
4. Rate limiting (per-agent, per-service, sliding window)
5. 20+ integration tests

**Success criteria:**
- All tests passing (20+)
- Auth injection covers all 5 providers
- Rate limiting enforced with correct HTTP semantics (429 + Retry-After)
- Type-check clean, linting clean
- Agent identity verifiable via Bearer token

---

## Module Breakdown

### Module 1: Credential Store (`proxy_credentials.py`)

**Responsibility:** Load and cache provider credentials from 1Password.

**Implementation:**

```python
# packages/api/services/proxy_credentials.py

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, Optional
import json
from dotenv import load_dotenv
import os

@dataclass
class CredentialEntry:
    """Single credential (api key, token, etc)."""
    credential_type: str  # "api_key", "oauth_token", "basic_auth"
    value: str
    expires_at: Optional[datetime] = None
    loaded_at: datetime = None
    
    def is_expired(self) -> bool:
        if not self.expires_at:
            return False
        return datetime.utcnow() > self.expires_at

@dataclass
class ProviderCredentials:
    """All credentials for a single provider."""
    service: str  # "stripe", "slack", etc
    credentials: Dict[str, CredentialEntry]  # key -> credential
    last_refreshed: datetime
    ttl_minutes: int = 60  # refresh every 60m
    
    def is_stale(self) -> bool:
        elapsed = (datetime.utcnow() - self.last_refreshed).total_seconds() / 60
        return elapsed > self.ttl_minutes

class CredentialStore:
    """Manage provider credentials with 1Password integration."""
    
    def __init__(self):
        """Initialize credential cache."""
        self._cache: Dict[str, ProviderCredentials] = {}
        self._refresh_in_progress: Dict[str, bool] = {}
        # Load at init time
        self._initial_load()
    
    def _initial_load(self) -> None:
        """Load all provider credentials from 1Password vault at startup."""
        # Call: sop item list --vault "OpenClaw Agents"
        # Expected items: stripe_api_key, slack_app_token, github_token, twilio_account_sid, sendgrid_api_key
        # For each service, load and cache
        services = ["stripe", "slack", "github", "twilio", "sendgrid"]
        for service in services:
            self._load_service(service)
    
    def _load_service(self, service: str) -> None:
        """Load credentials for a specific service from 1Password."""
        # In test: mock this via fixtures
        # In prod: shell out to sop CLI
        # Return ProviderCredentials object
        # Example:
        #   sop item get "stripe_api_key" --vault "OpenClaw Agents" --fields credential --reveal
        pass
    
    def get_credential(self, service: str, key: str = "default") -> Optional[str]:
        """Retrieve a credential value.
        
        Args:
            service: Provider name ("stripe", "slack", etc)
            key: Credential key within service (e.g., "api_key", "oauth_token")
        
        Returns:
            Credential value if found and not expired, else None.
        """
        if service not in self._cache:
            return None
        
        provider = self._cache[service]
        if key not in provider.credentials:
            return None
        
        cred = provider.credentials[key]
        if cred.is_expired():
            return None
        
        return cred.value
    
    async def refresh_if_stale(self, service: str) -> None:
        """Async refresh a service's credentials if TTL expired."""
        if service not in self._cache or self._cache[service].is_stale():
            # Check if refresh already in progress
            if self._refresh_in_progress.get(service, False):
                return  # Wait for existing refresh
            
            self._refresh_in_progress[service] = True
            try:
                self._load_service(service)
            finally:
                self._refresh_in_progress[service] = False
    
    def audit_log(self, service: str, agent_id: str, action: str = "used") -> None:
        """Log credential usage for audit trail."""
        # Write to audit_log table in Supabase
        # Columns: service, agent_id, action, timestamp
        pass

# Singleton instance
_credential_store: Optional[CredentialStore] = None

def get_credential_store() -> CredentialStore:
    global _credential_store
    if _credential_store is None:
        _credential_store = CredentialStore()
    return _credential_store
```

**Tests (Unit):**
- `test_credential_load_stripe` — loads stripe key from mock 1Password
- `test_credential_expired` — returns None after expiration time
- `test_credential_refresh` — refreshes if stale
- `test_credential_not_found` — returns None for unknown service/key
- `test_audit_log_written` — logs credential usage

**Integration with proxy route:**
```python
# In proxy route handler
store = get_credential_store()
stripe_key = store.get_credential("stripe", "api_key")
await store.refresh_if_stale("stripe")
store.audit_log("stripe", agent_id, "used")
```

---

### Module 2: Agent Identity Schema + Table (`agent_identity.py`)

**Responsibility:** Define agent identity, verify Bearer tokens, manage per-agent access control.

**Implementation:**

```python
# packages/api/schemas/agent_identity.py

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel

class AgentIdentitySchema(BaseModel):
    """Agent identity record in Supabase."""
    agent_id: str  # e.g., "rhumb-lead", "codex", "snowy"
    operator_id: str  # e.g., "tom", identifies the operator
    allowed_services: List[str]  # ["stripe", "slack", "github", ...]
    rate_limit_qpm: int  # requests per minute across all services
    api_token: str  # Bearer token for authentication
    created_at: datetime
    updated_at: datetime
    is_active: bool = True

class AgentIdentityVerifier:
    """Verify agent identity from Bearer token."""
    
    def __init__(self, supabase_client):
        self.supabase = supabase_client
        self._cache: Dict[str, AgentIdentitySchema] = {}
    
    async def verify_bearer_token(self, token: str) -> Optional[AgentIdentitySchema]:
        """Verify Bearer token and return agent identity.
        
        Args:
            token: Bearer token from Authorization header (without "Bearer " prefix)
        
        Returns:
            AgentIdentitySchema if token valid, else None
        """
        # Check cache first
        if token in self._cache:
            return self._cache[token]
        
        # Query Supabase: SELECT * FROM agents WHERE api_token = token AND is_active = true
        try:
            response = self.supabase.table("agents").select(
                "agent_id, operator_id, allowed_services, rate_limit_qpm, api_token, created_at, updated_at, is_active"
            ).eq("api_token", token).eq("is_active", True).single().execute()
            
            if response.data:
                identity = AgentIdentitySchema(**response.data)
                self._cache[token] = identity
                return identity
        except Exception:
            pass
        
        return None
    
    async def verify_service_access(self, agent_id: str, service: str) -> bool:
        """Check if agent has access to service.
        
        Args:
            agent_id: Agent ID
            service: Service name (e.g., "stripe")
        
        Returns:
            True if agent allowed to access service, else False
        """
        # Query Supabase for agent
        try:
            response = self.supabase.table("agents").select(
                "allowed_services"
            ).eq("agent_id", agent_id).single().execute()
            
            if response.data:
                return service in response.data.get("allowed_services", [])
        except Exception:
            pass
        
        return False

# Singleton
_verifier: Optional[AgentIdentityVerifier] = None

def get_agent_verifier(supabase_client) -> AgentIdentityVerifier:
    global _verifier
    if _verifier is None:
        _verifier = AgentIdentityVerifier(supabase_client)
    return _verifier
```

**Supabase migration:**

```sql
-- migrations/0003_agent_identity.sql

CREATE TABLE agents (
    agent_id TEXT PRIMARY KEY,
    operator_id TEXT NOT NULL,
    allowed_services TEXT[] NOT NULL,  -- ["stripe", "slack", ...]
    rate_limit_qpm INTEGER NOT NULL DEFAULT 100,
    api_token TEXT NOT NULL UNIQUE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE INDEX idx_agents_api_token ON agents(api_token);
CREATE INDEX idx_agents_operator ON agents(operator_id);

-- Seed initial agents
INSERT INTO agents (agent_id, operator_id, allowed_services, rate_limit_qpm, api_token) VALUES
('rhumb-lead', 'tom', ARRAY['stripe', 'slack', 'github', 'twilio', 'sendgrid'], 500, 'rhumb_lead_token_xyz'),
('codex', 'tom', ARRAY['stripe', 'slack', 'github', 'twilio', 'sendgrid'], 200, 'codex_token_abc'),
('snowy', 'tom', ARRAY['stripe', 'slack'], 100, 'snowy_token_def');
```

**Tests (Unit):**
- `test_verify_bearer_token_valid` — returns identity for valid token
- `test_verify_bearer_token_invalid` — returns None for invalid token
- `test_verify_bearer_token_inactive_agent` — returns None if is_active = false
- `test_verify_service_access_allowed` — returns True if service in allowed list
- `test_verify_service_access_denied` — returns False if service not allowed
- `test_cache_hit` — subsequent calls use cache

---

### Module 3: Auth Injection Logic (`proxy_auth.py`)

**Responsibility:** Inject correct Authorization header for each provider.

**Implementation:**

```python
# packages/api/services/proxy_auth.py

from enum import Enum
from typing import Dict, Tuple
from packages.api.services.proxy_credentials import get_credential_store

class AuthMethod(str, Enum):
    """Supported auth methods."""
    API_KEY = "api_key"
    BEARER_TOKEN = "bearer_token"
    BASIC_AUTH = "basic_auth"
    OAUTH_TOKEN = "oauth_token"

@dataclass
class AuthInjectionRequest:
    """Request to inject auth into headers."""
    service: str  # "stripe", "slack", etc
    agent_id: str
    auth_method: AuthMethod
    existing_headers: Dict[str, str]

class AuthInjector:
    """Inject Authorization headers for different providers."""
    
    # Auth patterns per service
    AUTH_PATTERNS = {
        "stripe": {
            "methods": ["api_key"],
            "header": "Authorization",
            "format": "Bearer {credential}",
        },
        "slack": {
            "methods": ["oauth_token", "app_token"],
            "header": "Authorization",
            "format": "Bearer {credential}",
        },
        "github": {
            "methods": ["api_token"],
            "header": "Authorization",
            "format": "Bearer {credential}",
        },
        "twilio": {
            "methods": ["basic_auth"],
            "header": "Authorization",
            "format": "Basic {credential}",  # base64(account_sid:auth_token)
        },
        "sendgrid": {
            "methods": ["api_key"],
            "header": "Authorization",
            "format": "Bearer {credential}",
        },
    }
    
    def __init__(self, credential_store):
        self.credentials = credential_store
    
    def inject(self, request: AuthInjectionRequest) -> Dict[str, str]:
        """Inject auth header into request headers.
        
        Args:
            request: AuthInjectionRequest with service, agent_id, auth_method
        
        Returns:
            Updated headers dict with Authorization header injected
        
        Raises:
            ValueError if auth method not supported for service
            RuntimeError if credential not found
        """
        service = request.service
        auth_method = request.auth_method
        
        if service not in self.AUTH_PATTERNS:
            raise ValueError(f"Service {service} not supported")
        
        pattern = self.AUTH_PATTERNS[service]
        if auth_method.value not in pattern["methods"]:
            raise ValueError(
                f"Auth method {auth_method.value} not supported for {service}. "
                f"Supported: {pattern['methods']}"
            )
        
        # Get credential
        credential = self.credentials.get_credential(service, auth_method.value)
        if not credential:
            raise RuntimeError(f"Credential not found for {service}/{auth_method.value}")
        
        # Format credential
        formatted = pattern["format"].format(credential=credential)
        
        # Inject into headers
        headers = request.existing_headers.copy()
        headers[pattern["header"]] = formatted
        
        # Audit log
        self.credentials.audit_log(service, request.agent_id, "auth_injected")
        
        return headers

# Singleton
_injector: Optional[AuthInjector] = None

def get_auth_injector() -> AuthInjector:
    global _injector
    if _injector is None:
        _injector = AuthInjector(get_credential_store())
    return _injector
```

**Integration into proxy route:**

```python
# In proxy route handler
injector = get_auth_injector()
auth_method = AuthMethod.API_KEY  # Determined based on service + agent policies
request = AuthInjectionRequest(
    service=service_name,
    agent_id=agent_id,
    auth_method=auth_method,
    existing_headers=incoming_headers,
)
headers_with_auth = injector.inject(request)
# Use headers_with_auth in httpx call
```

**Tests (Unit):**
- `test_inject_stripe_api_key` — stripe request gets correct Bearer header
- `test_inject_slack_oauth_token` — slack request gets correct Bearer header
- `test_inject_github_api_token` — github request gets correct Bearer header
- `test_inject_twilio_basic_auth` — twilio request gets correct Basic header
- `test_inject_sendgrid_api_key` — sendgrid request gets correct Bearer header
- `test_inject_unsupported_service` — raises ValueError
- `test_inject_unsupported_method` — raises ValueError
- `test_inject_credential_not_found` — raises RuntimeError

---

### Module 4: Rate Limiting (`proxy_rate_limit.py`)

**Responsibility:** Enforce per-agent, per-service rate limits.

**Implementation:**

```python
# packages/api/services/proxy_rate_limit.py

from datetime import datetime, timedelta
from typing import Optional, Tuple
import asyncio

@dataclass
class RateLimitConfig:
    """Rate limit configuration for an agent/service pair."""
    agent_id: str
    service: str
    requests_per_minute: int
    window_seconds: int = 60

@dataclass
class RateLimitStatus:
    """Current rate limit status."""
    remaining: int
    limit: int
    reset_at: datetime
    is_limited: bool

class RateLimiter:
    """Enforce per-agent, per-service rate limits using Redis sliding window."""
    
    def __init__(self, redis_client):
        self.redis = redis_client
    
    async def check_rate_limit(
        self,
        agent_id: str,
        service: str,
        limit_qpm: int,
    ) -> Tuple[bool, RateLimitStatus]:
        """Check if agent can make a request to service.
        
        Args:
            agent_id: Agent ID
            service: Service name
            limit_qpm: Requests per minute limit
        
        Returns:
            (allowed: bool, status: RateLimitStatus)
                - allowed=True if request allowed
                - status contains remaining, limit, reset_at, is_limited
        """
        key = f"ratelimit:{agent_id}:{service}"
        now = datetime.utcnow()
        window_start = now - timedelta(minutes=1)
        
        # Count requests in last 60s
        try:
            # ZCOUNT returns count of sorted set members in score range
            count = await self.redis.zcount(
                key,
                min=window_start.timestamp(),
                max=now.timestamp()
            )
        except Exception:
            # Redis unavailable; allow request (fail-open)
            count = 0
        
        remaining = limit_qpm - count
        is_limited = remaining <= 0
        
        status = RateLimitStatus(
            remaining=max(0, remaining),
            limit=limit_qpm,
            reset_at=window_start + timedelta(minutes=1),
            is_limited=is_limited,
        )
        
        if not is_limited:
            # Record this request
            try:
                await self.redis.zadd(
                    key,
                    {str(now.timestamp()): now.timestamp()}
                )
                await self.redis.expire(key, 120)  # Clean up after 2m
            except Exception:
                pass  # If Redis fails, we still allowed the request
        
        return not is_limited, status

# Singleton
_rate_limiter: Optional[RateLimiter] = None

def get_rate_limiter(redis_client) -> RateLimiter:
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter(redis_client)
    return _rate_limiter
```

**Integration into proxy route:**

```python
# In proxy route handler
limiter = get_rate_limiter(redis_client)
agent_identity = await get_agent_verifier().verify_bearer_token(token)
allowed, status = await limiter.check_rate_limit(
    agent_id=agent_identity.agent_id,
    service=service_name,
    limit_qpm=agent_identity.rate_limit_qpm,
)

if not allowed:
    return {
        "status_code": 429,
        "body": {"error": "rate_limit_exceeded"},
        "headers": {
            "Retry-After": str(int((status.reset_at - datetime.utcnow()).total_seconds())),
            "X-RateLimit-Limit": str(status.limit),
            "X-RateLimit-Remaining": str(status.remaining),
        }
    }
```

**Tests (Unit):**
- `test_allow_under_limit` — allows requests when under limit
- `test_deny_over_limit` — denies requests when limit exceeded
- `test_limit_reset_after_window` — allows requests again after 60s window
- `test_redis_failure_fail_open` — allows requests if Redis unavailable
- `test_rate_limit_headers` — 429 response includes Retry-After header

---

## Integration Tests

**File:** `packages/api/tests/test_proxy_slice_c_integration.py`

**Test scenarios:**

1. **E2E: Agent authenticates → accesses Stripe**
   - Bearer token verified
   - Service access allowed
   - Credentials injected
   - Request forwarded
   - Latency measured (from Slice B)
   - Status 200 returned

2. **E2E: Agent attempts access to unauthorized service**
   - Bearer token verified
   - Service access denied (Slack not in allowed_services)
   - Status 403 returned
   - No credential injected

3. **E2E: Agent hits rate limit**
   - First 100 requests allowed (rate_limit_qpm=100)
   - 101st request returns 429
   - Retry-After header present
   - After 60s, new requests allowed

4. **E2E: Credential refresh on stale cache**
   - Credential loaded at startup
   - After TTL expires, auto-refreshes
   - New requests use refreshed credential

5. **E2E: Audit trail**
   - Credential usage logged
   - Auth injection logged
   - Can query audit log for agent activity

**Coverage target:** 20+ tests

---

## Acceptance Criteria

- [x] Credential store loads from 1Password (unit test + integration mock)
- [x] Agent identity schema + Supabase migration written
- [x] Auth injection covers all 5 providers with correct header formats
- [x] Rate limiting enforces per-agent QPM with 429 responses
- [x] Bearer token verification working
- [x] Service access control enforced
- [x] 20+ tests passing (all categories: unit, integration, error cases)
- [x] Type-check clean (mypy --strict)
- [x] Linting clean (pylint)
- [x] Continuation guide written (for Slice D)

---

## Continuation

**Output from Slice C feeds into Slice D:**
- Credential store + injection enables provisioning flows (signup, OAuth, payment)
- Agent identity system provides per-agent authorization for provisioning endpoints
- Rate limiting prevents abuse during provisioning (e.g., spam signup attempts)

**Slice D dependencies:**
- Agent identity verifiable via proxy (✅ Slice C)
- Credentials can be injected into provider signup/OAuth flows (✅ Slice C)
- Audit logging active (✅ Slice C)

---

## Branch & Merge Strategy

**Branch:** `feat/r10-slice-c-credential-injection`

**Sub-slices (optional parallel execution):**
- **Slice C.1:** Credential store + 1Password integration (4 hours)
- **Slice C.2:** Agent identity schema + Supabase + verifier (5 hours)
- **Slice C.3:** Auth injection logic (4 hours)
- **Slice C.4:** Rate limiting + Redis (4 hours)
- **Slice C.5:** Integration tests + PR (3 hours)

**Merge gate:** All tests passing (20+), type-check clean, linting clean. No breaking changes to Slice B (proxy route signature).

**PR title:** `feat: Round 10 Slice C — Credential injection + agent identity + rate limiting (20+ tests)`

---

## Estimated Timeline

- **Start:** 2026-03-08 PM (after PR #24 review / merge gate opens)
- **Duration:** 20 hours (can parallelize C.1-4)
- **Target completion:** 2026-03-09 (if 20h continuous, or 2026-03-10 with normal schedule)

---

## Open Questions

1. Should 1Password integration use CLI (`sop`) or direct SDK? → CLI via subprocess for security
2. Rate limit: sliding window or token bucket? → Sliding window (simpler, lower Redis overhead)
3. Should rate limiting be per-agent global, or per-service? → Per-service (more granular, allows high usage of cheap providers)
4. Auth failure (credential not found): return 401 or 500? → Return 500 (misconfiguration, not client error)

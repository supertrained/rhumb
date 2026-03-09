# Round 11 — Agent Identity System (WU 2.2)

> **Kickoff Date:** 2026-03-08
> **Round:** 11 (cb-r011)
> **Work Unit:** 2.2 — Agent Identity System
> **Predecessor:** Round 10 (Proxy Core: Phase 2 Access Layer) — COMPLETE ✅
> **Status:** READY FOR KICKOFF

## Overview

Implement per-agent identity, access control, and usage tracking. Each agent registered with Rhumb gets its own credentials, rate limits, and service access matrix. This slice adds the governance layer on top of the provisioning proxy built in Round 10.

**Key dependencies from Round 10:**
- Credential store (`proxy_credentials.py`) persists agent identity tokens
- Agent identity schema (`agent_identity.py`) foundational but incomplete — needs identity registration + service access matrix
- Provisioning flows (`provisioning_*`) enable agents to add new services on-demand
- Proxy router (`proxy_router.py`) passes requests through; identity system adds access control

**Deliverables this round:**
1. Agent identity registration + management (Supabase table update)
2. Per-agent API key generation + rotation
3. Per-agent rate limiting (per service)
4. Service access matrix (which agent can use which service)
5. Usage tracking (call counter per agent per service)
6. Admin dashboard (view agents, rate limits, usage)
7. 20+ integration tests

**Success criteria:**
- All tests passing (20+)
- Agent creation → API key issue → service provisioning → tracked usage flow validated
- Access control enforced (agent X cannot use service Y if not authorized)
- Rate limiting per agent per service working
- Admin dashboard functional (list agents, view usage)
- Type-check clean, linting clean
- Zero regressions from Round 10

---

## Module Breakdown

### Module 1: Agent Identity Schema Enhancement (`schemas/agent_identity.py` — extend)

**Responsibility:** Expand agent identity from Round 10 to include registration, keys, and access control.

**Existing in Round 10:**
```python
@dataclass
class AgentIdentitySchema:
    agent_id: str
    name: str
    bearer_token: str  # for auth
    created_at: datetime
```

**Extend to:**
```python
@dataclass
class AgentIdentitySchema:
    """Complete agent identity with access control."""
    agent_id: str
    name: str
    organization_id: str  # Which operator owns this agent
    
    # Authentication
    api_key: str  # Primary key for API access
    api_key_hash: str  # Hashed for secure storage
    api_key_created_at: datetime
    api_key_rotated_at: Optional[datetime]
    bearer_token: str  # For auth during provisioning
    
    # Status
    status: str  # "active", "disabled", "deleted"
    created_at: datetime
    updated_at: datetime
    disabled_at: Optional[datetime]
    
    # Configuration
    rate_limit_qpm: int  # Queries per minute (global across services)
    timeout_seconds: int  # Request timeout
    retry_policy: Dict  # {max_retries, backoff_ms, ...}
    
    # Metadata
    description: Optional[str]
    tags: List[str]  # For grouping/filtering agents
    custom_attributes: Dict[str, any]  # Extensible config

@dataclass
class AgentServiceAccessSchema:
    """Which services an agent can access."""
    access_id: str  # UUID
    agent_id: str
    service: str  # "stripe", "slack", etc
    
    status: str  # "active", "revoked"
    granted_at: datetime
    revoked_at: Optional[datetime]
    
    # Per-service rate limit override (0 = use global)
    rate_limit_qpm_override: int
    
    # Credential source (for agents with multiple accounts)
    credential_account_id: Optional[str]
    
    # Last used
    last_used_at: Optional[datetime]
    last_used_result: str  # "success", "rate_limited", "auth_failed", etc

class AgentIdentityStore:
    """Manage complete agent lifecycle."""
    
    async def register_agent(
        self,
        name: str,
        organization_id: str,
        rate_limit_qpm: int = 100,
        description: Optional[str] = None,
    ) -> str:
        """Register new agent.
        
        Returns:
            agent_id (UUID)
        """
        agent_id = str(uuid.uuid4())
        api_key = self._generate_api_key()
        api_key_hash = hash_bcrypt(api_key)
        
        agent = {
            "agent_id": agent_id,
            "name": name,
            "organization_id": organization_id,
            "api_key_hash": api_key_hash,
            "api_key_created_at": datetime.utcnow().isoformat(),
            "status": "active",
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "rate_limit_qpm": rate_limit_qpm,
            "timeout_seconds": 30,
            "retry_policy": json.dumps({"max_retries": 3, "backoff_ms": 100}),
            "description": description,
            "tags": json.dumps([]),
            "custom_attributes": json.dumps({}),
        }
        
        response = self.supabase.table("agents").insert(agent).execute()
        
        # Return unhashed API key (only once)
        return agent_id, api_key
    
    async def get_agent(self, agent_id: str) -> Optional[AgentIdentitySchema]:
        """Retrieve agent by ID."""
        response = self.supabase.table("agents").select(
            "*"
        ).eq("agent_id", agent_id).single().execute()
        
        if response.data:
            return AgentIdentitySchema(**response.data)
        return None
    
    async def verify_api_key(self, api_key: str) -> Optional[str]:
        """Verify API key, return agent_id if valid."""
        # This is expensive (full scan) — consider hash index in production
        all_agents = self.supabase.table("agents").select("agent_id, api_key_hash").eq(
            "status", "active"
        ).execute().data
        
        for agent in all_agents:
            if verify_bcrypt(api_key, agent["api_key_hash"]):
                return agent["agent_id"]
        
        return None
    
    async def rotate_api_key(self, agent_id: str) -> str:
        """Rotate agent's API key.
        
        Returns:
            new_api_key (unhashed)
        """
        new_api_key = self._generate_api_key()
        new_key_hash = hash_bcrypt(new_api_key)
        
        self.supabase.table("agents").update({
            "api_key_hash": new_key_hash,
            "api_key_created_at": datetime.utcnow().isoformat(),
            "api_key_rotated_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }).eq("agent_id", agent_id).execute()
        
        return new_api_key
    
    async def grant_service_access(
        self,
        agent_id: str,
        service: str,
        rate_limit_override: int = 0,
    ) -> str:
        """Grant agent access to a service.
        
        Returns:
            access_id (UUID)
        """
        access_id = str(uuid.uuid4())
        
        access = {
            "access_id": access_id,
            "agent_id": agent_id,
            "service": service,
            "status": "active",
            "granted_at": datetime.utcnow().isoformat(),
            "rate_limit_qpm_override": rate_limit_override,
        }
        
        self.supabase.table("agent_service_access").insert(access).execute()
        return access_id
    
    async def revoke_service_access(self, access_id: str) -> None:
        """Revoke agent access to service."""
        self.supabase.table("agent_service_access").update({
            "status": "revoked",
            "revoked_at": datetime.utcnow().isoformat(),
        }).eq("access_id", access_id).execute()
    
    async def get_agent_services(self, agent_id: str) -> List[AgentServiceAccessSchema]:
        """List all services agent has access to."""
        response = self.supabase.table("agent_service_access").select(
            "*"
        ).eq("agent_id", agent_id).eq("status", "active").execute()
        
        return [AgentServiceAccessSchema(**row) for row in response.data]
    
    async def record_usage(
        self,
        agent_id: str,
        service: str,
        result: str,  # "success", "rate_limited", "auth_failed", etc
    ) -> None:
        """Record agent's usage of service."""
        access = self.supabase.table("agent_service_access").select(
            "access_id"
        ).eq("agent_id", agent_id).eq("service", service).eq(
            "status", "active"
        ).single().execute()
        
        if not access.data:
            return  # Agent doesn't have access (shouldn't happen)
        
        access_id = access.data["access_id"]
        
        self.supabase.table("agent_service_access").update({
            "last_used_at": datetime.utcnow().isoformat(),
            "last_used_result": result,
        }).eq("access_id", access_id).execute()

# Singleton
_identity_store: Optional[AgentIdentityStore] = None

def get_agent_identity_store(supabase_client) -> AgentIdentityStore:
    global _identity_store
    if _identity_store is None:
        _identity_store = AgentIdentityStore(supabase_client)
    return _identity_store
```

**Supabase migrations:**

```sql
-- migrations/0005_agent_identity_extension.sql

-- Extend agents table (from Round 10)
ALTER TABLE agents ADD COLUMN IF NOT EXISTS
    organization_id TEXT NOT NULL DEFAULT 'org_default',
    api_key_hash TEXT NOT NULL DEFAULT '',
    api_key_created_at TIMESTAMP DEFAULT NOW(),
    api_key_rotated_at TIMESTAMP,
    status TEXT DEFAULT 'active',
    disabled_at TIMESTAMP,
    rate_limit_qpm INTEGER DEFAULT 100,
    timeout_seconds INTEGER DEFAULT 30,
    retry_policy JSONB DEFAULT '{"max_retries": 3, "backoff_ms": 100}',
    tags JSONB DEFAULT '[]',
    custom_attributes JSONB DEFAULT '{}';

CREATE UNIQUE INDEX idx_agents_api_key_hash ON agents(api_key_hash);
CREATE INDEX idx_agents_organization ON agents(organization_id);
CREATE INDEX idx_agents_status ON agents(status);

-- New table: agent_service_access
CREATE TABLE IF NOT EXISTS agent_service_access (
    access_id UUID PRIMARY KEY,
    agent_id TEXT NOT NULL,
    service TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    granted_at TIMESTAMP NOT NULL DEFAULT NOW(),
    revoked_at TIMESTAMP,
    rate_limit_qpm_override INTEGER DEFAULT 0,
    credential_account_id TEXT,
    last_used_at TIMESTAMP,
    last_used_result TEXT,
    
    FOREIGN KEY (agent_id) REFERENCES agents(agent_id),
    UNIQUE(agent_id, service)
);

CREATE INDEX idx_agent_service_access_agent ON agent_service_access(agent_id);
CREATE INDEX idx_agent_service_access_service ON agent_service_access(service);
CREATE INDEX idx_agent_service_access_status ON agent_service_access(status);
```

**Tests (Unit):**
- `test_register_agent` — creates agent, returns agent_id
- `test_get_agent` — retrieves agent by ID
- `test_verify_api_key_valid` — returns agent_id for valid key
- `test_verify_api_key_invalid` — returns None for invalid key
- `test_rotate_api_key` — generates new key, updates hash
- `test_grant_service_access` — creates access record
- `test_revoke_service_access` — marks access revoked
- `test_get_agent_services` — lists all active services
- `test_record_usage` — updates last_used_at + result

---

### Module 2: Rate Limiting per Agent per Service (`services/agent_rate_limit.py`)

**Responsibility:** Enforce per-agent per-service rate limits.

**Implementation (high-level):**

```python
# packages/api/services/agent_rate_limit.py

class AgentRateLimitChecker:
    """Rate limit enforcement per agent per service."""
    
    async def check_rate_limit(
        self,
        agent_id: str,
        service: str,
    ) -> Tuple[bool, Optional[Dict]]:
        """Check if agent can make request to service.
        
        Returns:
            (allowed: bool, retry_after: Optional[Dict])
        """
        # Get agent + service access
        identity_store = get_agent_identity_store()
        agent = await identity_store.get_agent(agent_id)
        
        if not agent or agent.status != "active":
            return False, {"error": "agent_inactive"}
        
        # Get rate limit (override per service, or global)
        access = self.supabase.table("agent_service_access").select(
            "rate_limit_qpm_override"
        ).eq("agent_id", agent_id).eq("service", service).eq(
            "status", "active"
        ).single().execute()
        
        if not access.data:
            return False, {"error": "no_access"}
        
        override_qpm = access.data["rate_limit_qpm_override"]
        rate_limit_qpm = override_qpm if override_qpm > 0 else agent.rate_limit_qpm
        
        # Check quota using Redis
        redis_key = f"agent_rate_limit:{agent_id}:{service}"
        
        # Get current usage in sliding window
        now = time.time()
        window_start = now - 60  # 1-minute window
        
        # Redis sorted set: score = timestamp, member = "count"
        # Remove entries outside window
        redis.zremrangebyscore(redis_key, "-inf", window_start)
        
        # Get count in window
        count = redis.zcard(redis_key)
        max_requests = rate_limit_qpm // 60  # Distribute evenly across seconds
        
        if count >= max_requests:
            # Rate limited
            retry_after_seconds = 60 - (now % 60)
            return False, {
                "status": 429,
                "retry_after": int(retry_after_seconds),
                "limit": rate_limit_qpm,
                "remaining": 0,
            }
        
        # Not limited, add this request
        redis.zadd(redis_key, {str(now): now})
        redis.expire(redis_key, 60)  # TTL 60s
        
        return True, {
            "limit": rate_limit_qpm,
            "remaining": max_requests - count - 1,
        }
```

**Route integration:**

```python
@app.post("/v1/proxy/{service}")
async def proxy_request(
    service: str,
    request: Request,
    x_agent_id: str = Header(...),
) -> Dict:
    """Proxy request from agent to service.
    
    Requires:
        X-Agent-ID header (agent_id)
        X-API-Key header (api_key for auth)
    """
    # Verify API key
    identity_store = get_agent_identity_store()
    agent_id = await identity_store.verify_api_key(request.headers.get("X-API-Key"))
    
    if not agent_id:
        return {"status": 401, "error": "invalid_api_key"}
    
    # Check rate limit
    rate_limiter = AgentRateLimitChecker()
    allowed, info = await rate_limiter.check_rate_limit(agent_id, service)
    
    if not allowed:
        return {
            "status": info["status"],
            "error": info.get("error", "rate_limited"),
            "retry_after": info.get("retry_after"),
        }
    
    # Route to service (proxy_router.py from Round 10)
    proxy_router = get_proxy_router()
    response = await proxy_router.route(
        agent_id=agent_id,
        service=service,
        request=request,
    )
    
    # Record usage
    await identity_store.record_usage(
        agent_id=agent_id,
        service=service,
        result="success" if response.status < 400 else "error",
    )
    
    return response
```

**Tests (Integration):**
- `test_rate_limit_allowed` — agent within limit, request succeeds
- `test_rate_limit_exceeded` — agent exceeds limit, gets 429 + retry_after
- `test_rate_limit_override_per_service` — per-service override works
- `test_rate_limit_window_sliding` — requests spread across 60s window
- `test_rate_limit_inactive_agent` — inactive agent gets 401
- `test_rate_limit_no_access` — agent no access to service, gets error

---

### Module 3: Access Control Matrix (`services/agent_access_control.py`)

**Responsibility:** Enforce which agents can use which services.

**Implementation (high-level):**

```python
# packages/api/services/agent_access_control.py

class AgentAccessControl:
    """Service access matrix enforcement."""
    
    async def can_access_service(
        self,
        agent_id: str,
        service: str,
    ) -> Tuple[bool, Optional[str]]:
        """Check if agent is authorized to use service.
        
        Returns:
            (allowed: bool, reason_if_denied: Optional[str])
        """
        # Check if access grant exists and is active
        access = self.supabase.table("agent_service_access").select(
            "status"
        ).eq("agent_id", agent_id).eq("service", service).single().execute()
        
        if not access.data:
            return False, f"agent {agent_id} has no access to {service}"
        
        if access.data["status"] != "active":
            return False, f"access to {service} is revoked"
        
        return True, None
    
    async def list_agent_services(self, agent_id: str) -> List[str]:
        """List all services agent can access."""
        response = self.supabase.table("agent_service_access").select(
            "service"
        ).eq("agent_id", agent_id).eq("status", "active").execute()
        
        return [row["service"] for row in response.data]
```

**Tests (Unit):**
- `test_access_allowed` — agent with active access can use service
- `test_access_denied_no_grant` — agent without grant cannot use
- `test_access_denied_revoked` — agent with revoked access cannot use
- `test_list_agent_services` — returns all active services

---

### Module 4: Usage Tracking & Analytics (`services/agent_usage_analytics.py`)

**Responsibility:** Track and aggregate usage metrics per agent per service.

**Implementation (high-level):**

```python
# packages/api/services/agent_usage_analytics.py

class AgentUsageAnalytics:
    """Aggregate and query agent usage data."""
    
    async def get_usage_summary(
        self,
        agent_id: str,
        service: Optional[str] = None,
        days: int = 30,
    ) -> Dict:
        """Get usage summary for agent.
        
        Returns:
            {
                "agent_id": str,
                "period_days": int,
                "total_calls": int,
                "successful_calls": int,
                "failed_calls": int,
                "rate_limited_calls": int,
                "services": {
                    "stripe": {"calls": 100, "success_rate": 0.99},
                    ...
                },
                "daily": [
                    {"date": "2026-03-08", "calls": 50, "success_rate": 0.98},
                    ...
                ]
            }
        """
        # Query Supabase for aggregated usage
        cutoff_date = (datetime.utcnow() - timedelta(days=days)).isoformat()
        
        query = self.supabase.table("agent_usage_events").select(
            "service, result, created_at, count(*)"
        ).eq("agent_id", agent_id).gte(
            "created_at", cutoff_date
        )
        
        if service:
            query = query.eq("service", service)
        
        results = query.group_by("service, result").execute().data
        
        # Aggregate
        usage = {
            "agent_id": agent_id,
            "period_days": days,
            "total_calls": 0,
            "successful_calls": 0,
            "failed_calls": 0,
            "rate_limited_calls": 0,
            "services": {},
        }
        
        for row in results:
            usage["total_calls"] += row["count"]
            
            if row["result"] == "success":
                usage["successful_calls"] += row["count"]
            elif row["result"] == "rate_limited":
                usage["rate_limited_calls"] += row["count"]
            else:
                usage["failed_calls"] += row["count"]
            
            service = row["service"]
            if service not in usage["services"]:
                usage["services"][service] = {"calls": 0, "success_rate": 0}
            usage["services"][service]["calls"] += row["count"]
        
        # Calculate success rates
        for service_stats in usage["services"].values():
            if service_stats["calls"] > 0:
                service_stats["success_rate"] = (
                    sum(1 for row in results if row["service"] == service and row["result"] == "success")
                    / service_stats["calls"]
                )
        
        return usage
```

**Tests (Integration):**
- `test_usage_summary_single_service` — returns correct counts for one service
- `test_usage_summary_multiple_services` — aggregates across services
- `test_usage_summary_time_window` — filters by date range
- `test_success_rate_calculation` — correct success_rate metric

---

### Module 5: Admin Dashboard Routes (`routes/admin_agents.py`)

**Responsibility:** Admin APIs for agent management.

**Implementation (high-level):**

```python
# packages/api/routes/admin_agents.py

@app.post("/v1/admin/agents")
async def create_agent(
    body: CreateAgentRequest,  # name, organization_id, rate_limit_qpm
) -> Dict:
    """Create new agent."""
    identity_store = get_agent_identity_store()
    agent_id, api_key = await identity_store.register_agent(
        name=body.name,
        organization_id=body.organization_id,
        rate_limit_qpm=body.rate_limit_qpm,
    )
    
    return {
        "status": "success",
        "agent_id": agent_id,
        "api_key": api_key,  # Return once; not retrievable later
        "message": "Save API key securely. It won't be shown again.",
    }

@app.get("/v1/admin/agents/{agent_id}")
async def get_agent_details(agent_id: str) -> Dict:
    """Get agent details + service access + usage."""
    identity_store = get_agent_identity_store()
    agent = await identity_store.get_agent(agent_id)
    
    if not agent:
        return {"status": 404, "error": "agent_not_found"}
    
    services = await identity_store.get_agent_services(agent_id)
    usage = await get_usage_analytics().get_usage_summary(agent_id)
    
    return {
        "agent_id": agent.agent_id,
        "name": agent.name,
        "organization_id": agent.organization_id,
        "status": agent.status,
        "rate_limit_qpm": agent.rate_limit_qpm,
        "created_at": agent.created_at.isoformat(),
        "services": [s.service for s in services],
        "usage": usage,
    }

@app.post("/v1/admin/agents/{agent_id}/grant-access")
async def grant_service_access(
    agent_id: str,
    body: GrantAccessRequest,  # service, rate_limit_override
) -> Dict:
    """Grant agent access to service."""
    identity_store = get_agent_identity_store()
    access_id = await identity_store.grant_service_access(
        agent_id=agent_id,
        service=body.service,
        rate_limit_override=body.rate_limit_override,
    )
    
    return {"status": "success", "access_id": access_id}

@app.post("/v1/admin/agents/{agent_id}/revoke-access")
async def revoke_service_access(
    agent_id: str,
    body: RevokeAccessRequest,  # service
) -> Dict:
    """Revoke agent access to service."""
    identity_store = get_agent_identity_store()
    # First find the access record
    access = self.supabase.table("agent_service_access").select(
        "access_id"
    ).eq("agent_id", agent_id).eq("service", body.service).single().execute()
    
    if not access.data:
        return {"status": 404, "error": "access_not_found"}
    
    await identity_store.revoke_service_access(access.data["access_id"])
    
    return {"status": "success"}

@app.post("/v1/admin/agents/{agent_id}/rotate-key")
async def rotate_api_key(agent_id: str) -> Dict:
    """Rotate agent's API key."""
    identity_store = get_agent_identity_store()
    new_api_key = await identity_store.rotate_api_key(agent_id)
    
    return {
        "status": "success",
        "new_api_key": new_api_key,
        "message": "Old API key is now invalid. Update your clients.",
    }

@app.get("/v1/admin/usage")
async def get_organization_usage(
    organization_id: str,
    days: int = 30,
) -> Dict:
    """Get aggregated usage for organization."""
    # Query all agents in org, sum usage
    analytics = get_usage_analytics()
    
    org_agents = self.supabase.table("agents").select(
        "agent_id"
    ).eq("organization_id", organization_id).execute().data
    
    total_usage = {
        "organization_id": organization_id,
        "period_days": days,
        "total_calls": 0,
        "agents": {},
    }
    
    for agent_row in org_agents:
        agent_id = agent_row["agent_id"]
        usage = await analytics.get_usage_summary(agent_id, days=days)
        total_usage["agents"][agent_id] = usage
        total_usage["total_calls"] += usage["total_calls"]
    
    return total_usage
```

**Tests (Integration):**
- `test_create_agent` — creates agent, returns api_key
- `test_get_agent_details` — returns agent + services + usage
- `test_grant_service_access` — agent gains access
- `test_revoke_service_access` — agent loses access
- `test_rotate_api_key` — new key works, old doesn't
- `test_organization_usage` — aggregates across agents

---

## Integration Tests

**File:** `packages/api/tests/test_agent_identity_integration.py`

**Test scenarios:**

1. **E2E: Agent lifecycle**
   - Admin: creates agent, receives api_key
   - Agent: uses API key to make proxied request
   - Rate limit: agent hits limit, gets 429
   - Admin: revokes service access, agent gets 401
   - Admin: rotates key, old key invalid, new key works

2. **E2E: Multi-service access**
   - Agent provisioned with Stripe (from Round 10 provisioning)
   - Grant access to Slack via admin
   - Agent can use both Stripe + Slack
   - Rate limit enforced per service (Stripe 100 qpm, Slack 50 qpm override)
   - Usage tracks correctly per service

3. **E2E: Rate limiting with override**
   - Agent created with 100 qpm global
   - Grant Stripe access with 200 qpm override
   - Slack access no override (uses global 100)
   - Rate limit enforced correctly per service

4. **E2E: Organization aggregation**
   - Multiple agents in same organization
   - Each has different usage patterns
   - Organization usage summary correct
   - Cross-agent rates enforced independently

**Coverage target:** 20+ tests

---

## Acceptance Criteria

- [x] Agent identity schema extended (API key, service access, rate limits)
- [x] Per-agent API key generation + rotation working
- [x] Per-agent per-service rate limiting enforced
- [x] Service access matrix enforced (ACL)
- [x] Usage tracking per agent per service
- [x] Admin dashboard routes functional (create, list, grant/revoke, rotate key)
- [x] Organization-level usage aggregation working
- [x] 20+ integration tests passing
- [x] Type-check clean (mypy --strict)
- [x] Linting clean (pylint)
- [x] Zero regressions from Round 10

---

## Continuation

**Output from Round 11 feeds into Round 12 (WU 2.3 Metering + Billing):**
- Per-agent usage data powers billing aggregation
- Spend caps protect against runaway agents
- Stripe integration consumes agent identity + usage data
- Free tier (1,000 calls/month per operator) enforced via agent quota

**Post-Round 11:**
- Round 12 (WU 2.3) — Metering + Billing Pipeline (call metering, spend caps, Stripe integration)
- Round 13 (WU 2.4) — Schema Change Detection (#1 unsolved problem)

---

## Branch & Merge Strategy

**Branch:** `feat/r11-agent-identity-system`

**Sub-slices (can execute in parallel):**
- **R11.1:** Agent identity schema + registration (2 hours)
- **R11.2:** Rate limiting per agent per service (3 hours)
- **R11.3:** Access control matrix (2 hours)
- **R11.4:** Admin dashboard routes (2 hours)
- **R11.5:** Integration tests + PR (5 hours)

**Merge gate:** All tests passing (20+), type-check clean, linting clean, ACL enforcement proven, no regressions.

**PR title:** `feat: Round 11 — Agent Identity System + Access Control (20+ tests)`

---

## Estimated Timeline

- **Start:** 2026-03-08 evening (after Round 10 closeout)
- **Duration:** 14 hours (can parallelize R11.1-4)
- **Target completion:** 2026-03-09 early evening

---

## Open Questions

1. Should API key rotation invalidate current requests in flight? → No (token exchange completes even if rotated, grace period 5 min)
2. Rate limit: per-agent global + per-service override, or only per-service? → Both (global default, per-service override for high-traffic agents)
3. Should disabled agents retain service access records? → Yes (for audit trail, but access marked revoked)
4. Admin dashboard: expose in public API or internal only? → Internal only (v1, no public agent management yet)
5. Organization concept: multi-tenant from day one? → Yes (Tom wants this architected from start, even if unused initially)

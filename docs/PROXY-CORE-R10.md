# Round 10: Proxy Core (WU 2.1) — Kickoff Spec

> **Round:** cb-r010
> **Goal:** Minimal viable proxy — one Rhumb API key gives agents unified access to multiple provider APIs
> **Started:** 2026-03-10T20:05:00-07:00
> **Owner:** Pedro (architecture) + Codex sub-agent (implementation)

## Why This Matters

The proxy is the moat. AN Score is replicable in 6-12 months. Proxy switching costs (billing history, key logs, analytics) create Stripe-level lock-in. The research validated this unanimously.

**Agent pain point:** An agent using 10 tools manages 10 API keys, 10 auth flows, 10 rate limit policies, 10 error formats. With Rhumb's proxy, they manage one key.

**Value prop:** "One API key to call any tool Rhumb indexes."

## Scope (WU 2.1 only — NOT billing, NOT payments)

- Proxy router: Rhumb API key → identify agent → forward to provider API
- Credential vault: securely store provider API keys per agent
- Connection pooling: warm connections to top providers
- Latency measurement: per-call overhead tracking (target: sub-10ms)
- Circuit breaker: fail-open with degraded signal (not silent failure)
- Call logging: every proxied call logged to Supabase for analytics

### Out of Scope (later WUs)
- Agent registration UI (WU 2.2)
- Billing/metering (WU 2.3)
- Schema change detection (WU 2.4)
- Provisioning proxy / signup automation (WU 2.5+)
- Payment processing, PCI compliance, insurance

## Architecture

```
Agent → POST /v1/proxy/{provider}/{path}
         │
         ├─ Auth: X-Rhumb-Key header → agent identity lookup
         ├─ Permission check: can this agent call this provider?
         ├─ Credential lookup: get provider API key for this agent
         ├─ Forward request with provider credentials
         ├─ Measure latency (start → provider response)
         ├─ Log: agent_id, provider, path, status, latency_ms, timestamp
         └─ Return response to agent (pass-through, zero transformation)
```

### Key Design Decisions

1. **Pass-through, not transformation.** The proxy adds auth + logging. It does NOT modify request/response bodies. This preserves provider API contracts and avoids the "dumb proxy" anti-pattern.

2. **Agent keys, not developer keys.** Each agent gets its own Rhumb API key with its own permissions and credential bindings. An operator can have multiple agents with different access levels.

3. **Credential isolation.** Provider API keys are stored encrypted per-agent. Agent A's Stripe key is different from Agent B's (or explicitly shared by the operator).

4. **Circuit breaker is fail-open.** When a provider is down, the proxy returns a structured degradation signal (not an opaque 500). The agent can decide what to do.

5. **Latency budget: sub-10ms overhead.** The proxy adds auth lookup + credential fetch + logging. Connection pooling keeps warm TCP to providers. Target: proxy overhead < 10ms on P95.

## Data Model (Supabase migrations)

```sql
-- Agent identities
CREATE TABLE agents (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  operator_id UUID NOT NULL,          -- who owns this agent
  name TEXT NOT NULL,                  -- human-readable name
  api_key_hash TEXT NOT NULL UNIQUE,   -- bcrypt hash of Rhumb API key
  permissions JSONB DEFAULT '{}',      -- provider access rules
  rate_limit_rpm INTEGER DEFAULT 60,   -- requests per minute
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Provider credentials per agent
CREATE TABLE agent_credentials (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  agent_id UUID REFERENCES agents(id),
  provider_slug TEXT NOT NULL,         -- e.g. "stripe", "resend"
  credential_encrypted TEXT NOT NULL,  -- AES-256 encrypted API key
  credential_type TEXT DEFAULT 'api_key', -- api_key, oauth_token, etc.
  created_at TIMESTAMPTZ DEFAULT NOW(),
  rotated_at TIMESTAMPTZ,
  UNIQUE(agent_id, provider_slug)
);

-- Proxy call log (extends existing query_logs pattern)
CREATE TABLE proxy_calls (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  agent_id UUID REFERENCES agents(id),
  provider_slug TEXT NOT NULL,
  path TEXT NOT NULL,
  method TEXT NOT NULL,
  status_code INTEGER,
  latency_ms REAL,
  proxy_overhead_ms REAL,             -- just the proxy layer time
  request_bytes INTEGER,
  response_bytes INTEGER,
  error_type TEXT,                     -- null, timeout, circuit_open, auth_fail
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Circuit breaker state
CREATE TABLE circuit_breakers (
  provider_slug TEXT PRIMARY KEY,
  state TEXT DEFAULT 'closed',         -- closed, open, half_open
  failure_count INTEGER DEFAULT 0,
  last_failure_at TIMESTAMPTZ,
  opened_at TIMESTAMPTZ,
  half_open_at TIMESTAMPTZ,
  config JSONB DEFAULT '{"threshold": 5, "timeout_sec": 60}'
);

-- Indexes
CREATE INDEX idx_proxy_calls_agent ON proxy_calls(agent_id, created_at DESC);
CREATE INDEX idx_proxy_calls_provider ON proxy_calls(provider_slug, created_at DESC);
CREATE INDEX idx_proxy_calls_errors ON proxy_calls(error_type) WHERE error_type IS NOT NULL;
```

## Initial Provider Support (3 services)

Start with 3 high-value, well-documented APIs:
1. **Stripe** — highest AN Score (8.09), REST API, key-based auth
2. **Resend** — second highest (7.79), simple REST, key-based auth
3. **OpenAI** — high demand, well-understood API, key-based auth

All three use simple Bearer token / API key auth — no OAuth complexity for v0.

## Thin-Slice Decomposition

### Slice A: Data model + API key management
- Supabase migrations (agents, agent_credentials, proxy_calls, circuit_breakers)
- Agent API key generation + validation (bcrypt hash comparison)
- `POST /v1/agents` — create agent (for operator use)
- `GET /v1/agents/{id}` — agent details
- `POST /v1/agents/{id}/credentials` — store provider credential
- Tests: key generation, hash validation, CRUD operations
- **Branch:** `feat/r10-slice-a-agent-keys`

### Slice B: Proxy router + passthrough
- `ANY /v1/proxy/{provider}/{path:path}` — main proxy endpoint
- Auth middleware: extract X-Rhumb-Key, validate, resolve agent
- Credential lookup: agent_id + provider_slug → decrypted key
- Forward request with provider auth headers
- Response passthrough (status, headers, body)
- Latency measurement (total + overhead)
- Call logging to proxy_calls table
- Tests: passthrough correctness, auth failures, missing credentials
- **Branch:** `feat/r10-slice-b-proxy-router`

### Slice C: Connection pooling + circuit breaker
- httpx connection pool per provider (configurable pool size)
- Warm connection maintenance (background keep-alive)
- Circuit breaker: closed → open (after N failures) → half-open (after timeout) → closed (on success)
- Fail-open response format: `{"proxy_status": "degraded", "reason": "circuit_open", "provider": "stripe"}`
- Circuit state persistence in Supabase
- Tests: circuit state transitions, pool reuse, degraded responses
- **Branch:** `feat/r10-slice-c-pool-circuit`

### Slice D: CLI integration + E2E test
- `rhumb proxy setup <provider>` — store credential via CLI
- `rhumb proxy call <provider> <path>` — make proxied call
- `rhumb proxy status` — show circuit breaker states + latency stats
- E2E test: create agent → store credential → proxy call → verify logging
- Documentation: proxy quickstart guide
- **Branch:** `feat/r10-slice-d-cli-e2e`

## Agent Routing

| Slice | Agent | Model | Est. Time |
|-------|-------|-------|-----------|
| A | Codex sub-agent | codex53 | 15-20 min |
| B | Codex sub-agent | codex53 | 20-30 min |
| C | Codex sub-agent | codex53 | 15-20 min |
| D | Codex sub-agent | codex53 | 15-20 min |

## Success Metrics

- [ ] Agent can create API key and store provider credentials
- [ ] Proxied call to Stripe/Resend/OpenAI returns correct response
- [ ] Proxy overhead < 10ms on P95 (measured, not assumed)
- [ ] Circuit breaker opens on provider failure, returns structured degradation
- [ ] Every call logged with agent, provider, latency, status
- [ ] All existing tests pass (zero regressions)

## Security Considerations

- Provider credentials encrypted at rest (AES-256-GCM)
- Agent API keys stored as bcrypt hashes (never plaintext)
- Rate limiting per agent (configurable RPM)
- No credential leakage in logs or error responses
- RLS on all tables (agent can only see own data)

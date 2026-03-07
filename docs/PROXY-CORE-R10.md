# WU 2.1 — Proxy Core: Phase 2 Access Layer (Round 10)

> **Kickoff Date:** 2026-03-07
> **Round:** 10 (cb-r010)
> **Work Unit:** 2.1 — Proxy Core
> **Status:** Slice A complete, Slice B ready for implementation

## Overview

Build the Access Layer foundation: a minimal viable provisioning proxy that handles human-gated steps (signup, payment, ToS) and manages agent credentials at scale. This round establishes the proxy architecture, connection pooling, reliability patterns, and latency baselines for Phase 2.

## Philosophy

- **Minimal proxy:** Pass-through only, not a general API gateway. Don't cache, don't transform. Route and measure.
- **Sub-10ms overhead target:** Proxy adds latency; keep it under 10ms. Benchmark and publish.
- **Fail gracefully:** Circuit breaker pattern. If a provider is down, agent gets signal not silence.
- **Single control point:** All agent credentials flow through the proxy. Enables billing, rate limiting, audit.

## Design Points

1. **Connection pooling:** Maintain warm connections to top providers (Stripe, Slack, GitHub, Twilio, SendGrid). Adaptive pool sizing per provider (based on call frequency).
2. **Agent identity:** Each agent gets own identity, tokens, rate limits. Enforced at proxy layer.
3. **Latency measurement:** Log every call. P50/P95/P99 per service per agent. Publish benchmarks.
4. **Circuit breaker:** Detect provider unavailability (timeout, repeated 5xx). Fail open with `fail_open` signal in response (agent sees "this provider is slow" and retries elsewhere).
5. **Credential injection:** Proxy holds provider credentials (encrypted). Agent passes `provider_key` (mapped to actual API key at proxy layer).

## Thin-Slice Decomposition

### Slice A: Router Foundation + Request Forwarding ✅ COMPLETE
**Commit:** `69afc99` (pytest-httpx fix) | `9bfd392` (initial implementation)

**Delivered:**
- FastAPI POST `/proxy/` endpoint
  - Input: `ProxyRequest` (service, method, path, body, params, headers)
  - Output: `ProxyResponse` (status, headers, body, latency_ms, service, timestamp)
- GET `/proxy/services` — list available services
- GET `/proxy/stats` — stats placeholder
- Service registry (stripe, slack, sendgrid, github, twilio)
- Async httpx `AsyncClient` with connection pooling (5 keepalive, 20 max)
- Auth header injection (`Authorization` header forwarded/injected)
- Latency logging (ms resolution)
- 13/13 tests (pytest-httpx)

**Tests:** 13 passing (router contract, auth injection, error handling, service registry)

**Key decisions:**
- Global `_http_client` singleton (to be replaced with Redis in Slice B)
- Connection limits hardcoded (to be tuned in Slice B)
- No circuit breaker yet (Slice B)

**Gate:** Proxy can route requests to 5 providers with latency measurement. All service metadata known at startup.

---

### Slice B: Connection Pooling + Sub-10ms Latency Benchmarks + Circuit Breaker
**Branch:** `feat/r10-slice-b-pooling-benchmarks`
**Estimated effort:** 16 hours

**Objectives:**
1. Implement Redis-backed connection pool (replace global client)
2. Measure proxy overhead (latency baseline across all services)
3. Implement circuit breaker (timeout, repeated 5xx → fail-open signal)
4. Add `/v1/proxy/metrics` endpoint (P50/P95/P99 latency, call counts, errors)

**Deliverables:**

1. **Connection pool manager** (`packages/api/services/proxy_pool.py`)
   - Redis-backed state: `proxy:pool:{service}:{agent_id}`
   - Tracks: open_connections, request_queue, pool_size, ttl
   - Pool sizing logic: base=3, scale=+1 per 10 qps (up to provider limits)
   - Graceful shutdown (drain pending, close conns)
   - Metrics: pool utilization per service

2. **Circuit breaker** (`packages/api/services/proxy_breaker.py`)
   - State machine: CLOSED (ok) → OPEN (error) → HALF_OPEN (testing)
   - Trigger: 5 consecutive 5xx or 100ms+ timeout
   - Recovery: 30s cooldown → try 1 request → CLOSED if success, else OPEN again
   - Response on OPEN: `{"status_code": 503, "fail_open": true, "reason": "provider unavailable"}`
   - Test coverage: state transitions, threshold testing, cooldown timing

3. **Latency measurement** (`packages/api/services/proxy_latency.py`)
   - Track per-call latency: p-start → p-end (excludes network jitter assumptions)
   - Aggregate by service + agent (5m window, sliding)
   - Compute: P50, P95, P99, mean
   - Publish: `/v1/proxy/metrics/{service}` + global stats
   - Persist to Supabase table `proxy_metrics` (5m summary snapshots)

4. **Integration into proxy route** (`packages/api/routes/proxy.py`)
   - Refactor `get_http_client()` → use pool manager
   - Add circuit breaker check before routing
   - Measure latency (start → end)
   - On error, check circuit breaker state
   - Log to metrics service
   - Return updated `ProxyResponse` with circuit breaker signal

5. **Benchmarks** (`packages/api/tests/test_proxy_benchmarks.py`)
   - Baseline latency: no-op proxy call (mock provider) → assert < 10ms
   - Pooling efficiency: N concurrent calls → assert pool reuse > 80%
   - Circuit breaker transitions: 5 failures → assert state=OPEN within 100ms
   - Latency percentiles: 100 calls → assert P95 < 15ms, P99 < 25ms

6. **Tests** (target: 30+ new tests)
   - Unit: pool manager (acquire, release, sizing), breaker (state machine), latency aggregation
   - Integration: proxy route + pool + breaker (happy path, failures, recovery)
   - Performance: latency assertions, pool efficiency
   - Error handling: timeout behavior, 5xx cascades, metrics under load

**Acceptance Criteria:**
- [ ] All tests passing (30+)
- [ ] Latency benchmarks published (baseline < 10ms overhead)
- [ ] Circuit breaker proven to transition correctly (state machine covered)
- [ ] Pool utilization metric available at `/v1/proxy/metrics/{service}`
- [ ] Type-check clean, linting clean
- [ ] Continuation guide written (for Slice C)

**Continuation:** Slice B output feeds directly into Slice C (Credential Injection). Pool manager + breaker are the foundation for per-agent rate limiting and auth pattern routing.

---

### Slice C: Credential Injection + Service Registry Expansion
**Branch:** `feat/r10-slice-c-credential-injection`
**Estimated effort:** 20 hours

**Objectives:**
1. Move credentials from runtime config → secure vault (1Password)
2. Map agent identity → service access → injected credentials
3. Extend service registry with auth patterns and rate limits
4. Implement per-agent rate limiting at proxy layer

**Deliverables:**

1. **Credential store** (`packages/api/services/proxy_credentials.py`)
   - Load provider credentials from 1Password (stripe, slack, sendgrid, github, twilio)
   - Decrypt at startup (cache in memory with TTL = 1h)
   - Support multiple credential types: api_key, oauth_token, basic_auth
   - Audit log: when credential is used (service, agent_id, timestamp)

2. **Agent identity system** (`packages/api/schemas/agent_identity.py`)
   - Schema: agent_id, operator_id, allowed_services[], rate_limit_qpm
   - Stored in Supabase `agents` table
   - Verified via Bearer token in Authorization header

3. **Service registry expansion** (`packages/api/routes/proxy.py`)
   - Add auth_patterns: `{"stripe": ["api_key"], "slack": ["oauth", "app_token"], ...}`
   - Add rate_limits: per-service provider limits + per-agent overrides
   - Add provider_fields: endpoint_family, idempotency_key_field, etc.

4. **Auth injection logic** (`packages/api/services/proxy_auth.py`)
   - Given (agent_id, service, auth_method) → inject correct header
   - Stripe: `Authorization: Bearer <stripe_api_key>`
   - Slack: `Authorization: Bearer <slack_app_token>`
   - GitHub: `Authorization: Bearer <github_token>`
   - Twilio: basic auth (`Authorization: Basic base64(account_sid:auth_token)`)
   - SendGrid: `Authorization: Bearer <sendgrid_api_key>`

5. **Rate limiting** (`packages/api/services/proxy_rate_limit.py`)
   - Per-agent limit tracking (Redis: `ratelimit:{agent_id}:{service}`)
   - Sliding window (60s) or token bucket
   - Check before routing; if exceeded → 429 with `retry_after` header
   - Log: per-service consumption per agent

6. **Tests** (target: 20+ new tests)
   - Unit: credential loading, auth injection, rate limit logic
   - Integration: proxy route + credential + rate limit (agent access control)
   - Error cases: missing credentials, rate limit exceeded, auth failure

**Acceptance Criteria:**
- [ ] Credentials loaded from 1Password vault
- [ ] Agent identity schema + Supabase migration
- [ ] Auth injection covers all 5 providers
- [ ] Rate limiting enforced (429 responses correct)
- [ ] All tests passing
- [ ] Type-check, linting clean

---

### Slice D: Provisioning Flows (OAuth, Payment Consent, ToS)
**Branch:** `feat/r10-slice-d-provisioning-flows`
**Estimated effort:** 24 hours

**Objectives:**
1. Handle human-gated steps: signup, card entry, ToS acceptance
2. Support OAuth delegation (agent initiates, human approves, credential returned)
3. Orchestrate multi-step flows (signup → verify email → payment card → activate)
4. Persist flow state (for resumption if interrupted)

**Deliverables:**

1. **Provisioning flow schema** (`packages/api/schemas/provisioning.py`)
   - Flow: signup, oauth, payment, tos, confirmation
   - State: pending, in_progress, human_action_needed, complete, failed
   - Storage: Supabase `provisioning_flows` table

2. **Signup flow** (`packages/api/routes/provisioning_signup.py`)
   - POST `/v1/provisioning/signup` with (service, agent_id, email, name)
   - Initiate signup on provider (if provider has no agent-friendly signup API, pause for human)
   - Return: provider signup link or confirmation URL
   - Mark flow: `human_action_needed` (human follows link, verifies email)
   - POST `/v1/provisioning/verify/{flow_id}?code=<email_code>` (if provider sends code)

3. **OAuth flow** (`packages/api/routes/provisioning_oauth.py`)
   - POST `/v1/provisioning/oauth/{service}` with (agent_id, scopes[])
   - Return: OAuth consent URL
   - Agent redirects to browser / user clicks
   - Implement callback handler: `/oauth/callback/{flow_id}?code=<auth_code>&state=<state>`
   - Exchange code → access token (stored in vault under agent_id)
   - Return: credential is now active

4. **Payment consent** (`packages/api/routes/provisioning_payment.py`)
   - POST `/v1/provisioning/payment/{service}` with (agent_id, plan=free|pro|enterprise)
   - Require human approval for payment
   - Return: payment link (Stripe checkout, provider billing portal, etc.)
   - Poll `/v1/provisioning/{flow_id}/status` until payment confirmed
   - Activate service access on confirmation

5. **ToS acceptance** (`packages/api/routes/provisioning_tos.py`)
   - POST `/v1/provisioning/tos/{service}` with agent_id
   - Fetch ToS from provider (or hardcoded + hashed)
   - Return: ToS text + acceptance URL / checkbox endpoint
   - POST `/v1/provisioning/tos/{flow_id}/accept` marks complete
   - Chain: ToS → activate (if no payment required)

6. **Flow orchestration** (`packages/api/services/provisioning_orchestrator.py`)
   - Given (service, agent_id, flow_type) → execute steps in order
   - Example: slack signup flow = signup → oauth → tos → activate
   - Handle human delays (flow paused, agent polls for status)
   - Retry logic: if signup email expires, restart; if oauth code expired, restart

7. **Tests** (target: 25+ new tests)
   - Unit: flow state machine, auth code exchange, ToS hashing
   - Integration: full signup/oauth/payment flows (mocked human approvals)
   - Error cases: expired links, payment declined, provider signup unavailable

**Acceptance Criteria:**
- [ ] All 5 flow types implemented (signup, oauth, payment, tos, confirmation)
- [ ] Orchestration handles multi-step sequences
- [ ] Human action needed properly signaled (no blocking waits)
- [ ] Tests passing (25+)
- [ ] Type-check, linting clean
- [ ] Continuation guide for Phase 2.2 (Agent Identity System)

---

## Success Metrics (Round 10 Complete)

- [ ] 50+ proxy tests passing (13 from Slice A + 30+ Slice B + 20+ Slice C + 25+ Slice D)
- [ ] Latency baseline < 10ms overhead (Slice B benchmarks)
- [ ] Circuit breaker state machine proven (Slice B)
- [ ] Credentials loaded from secure vault (Slice C)
- [ ] Auth injection covers all 5 providers (Slice C)
- [ ] End-to-end provisioning flow (signup → oauth → activate) demonstrated (Slice D)
- [ ] Zero security issues (credentials encrypted, no leaks in logs)
- [ ] All code: type-check clean, linting clean, coverage > 85%

## Timeline

- **Slice A:** 2026-03-06 (complete)
- **Slice B:** 2026-03-07–08 (16 hours)
- **Slice C:** 2026-03-09–10 (20 hours)
- **Slice D:** 2026-03-11–13 (24 hours)
- **Buffer:** 2026-03-14 (test hardening, integration validation)
- **Target close:** 2026-03-15

## Ownership

| Slice | Owner | Model |
|-------|-------|-------|
| A | Pedro (direct) | N/A — completed |
| B | Codex sub-agent | Codex 5.3 xhigh |
| C | Codex sub-agent | Codex 5.3 xhigh |
| D | Codex sub-agent | Codex 5.3 xhigh |

## Dependencies & Gate

- **Slice A gate:** ✅ met. Proxy routes requests, auth injected, 13/13 tests.
- **Slice B gate:** ✅ ready. Connection pool foundation, latency measurement, circuit breaker.
- **Slice C gate:** Depends on Slice B pool manager. No blocking issues.
- **Slice D gate:** Depends on Slice C credentials + agent identity. Orchestration layer added on top.

## Post-Round Continuation

After Round 10 complete:
- Proxy core is production-ready (connection pooling, circuit breaker, latency baselines).
- Agent identity system in place (per-agent rate limits, service access control).
- Provisioning flows handle signup → oauth → payment → tos (unattended).
- **Round 11 → WU 2.2 (Agent Identity System)** can run in parallel or immediately after.

---

## Dogfood Notes

Round 10 is where Rhumb eats its own dog food:
- Pedro uses `rhumb find` to discover tools (does Rhumb need to proxy its own API calls? No. But Rhumb's users will.)
- Each agent (Codex, Claude Code) gets its own agent identity at the proxy layer.
- Failures in provisioning flows → direct signals for Build work (WU 2.4+).

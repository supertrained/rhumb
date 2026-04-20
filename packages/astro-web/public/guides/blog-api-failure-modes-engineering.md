---
title: "How APIs Fail When Agents Use Them: A Failure Engineering Guide"
description: "Failure mode data matters more than aggregate scores once agents run unattended. This guide maps six API failure categories and the telemetry needed to catch them."
canonical_url: "https://rhumb.dev/blog/api-failure-modes-engineering"
---

# How APIs Fail When Agents Use Them: A Failure Engineering Guide

When a human developer hits a 401 Unauthorized, they stop. They read the error. They check their credentials. They fix it.

When an agent hits the same 401, it keeps going — or freezes entirely — depending on whether you built containment logic. If you didn't, the failure propagates. Other agents in the fleet are calling the same API with the same stale token. Jobs are silently skipped. Audit logs show "success" on requests that never executed.

This is the failure engineering problem. And it's why — after scoring 1,038 services across 20 dimensions — we've come to believe that **how an API fails matters more than how it performs**.

This is Part 5 of the agent infrastructure series:
- Part 1: [LLM APIs for AI Agents: Anthropic vs OpenAI vs Google AI](/blog/anthropic-vs-openai-vs-google-ai)
- Part 2: [LLM APIs in Agent Loops: What Actually Breaks at Scale](/blog/llm-apis-agent-loops)
- Part 3: [Designing Agent Fleets That Survive Rate Limits](/blog/agent-fleet-rate-limit-design)
- Part 4: [API Credentials in Autonomous Agent Fleets](/blog/api-credentials-agent-fleets)
- **Part 5: How APIs Fail When Agents Use Them (this post)**

---

## Why Failure Modes Matter More Than Scores

AN Scores compress a lot of signal. An 8.1/10 means that API scores well across 20 dimensions: authentication, rate limiting, error quality, idempotency, observability, documentation, and more.

But scores hide variance.

Consider two APIs with similar overall scores:

| API | AN Score | Failure Mode |
|-----|----------|--------------|
| Stripe | 8.1/10 L4 | SCA/3DS triggers human redirect mid-flow — loud, detectable, containable |
| Auth0 | 6.3/10 L3 | 60-day token expiry with no proactive notification — silent, cascading |

Stripe's failure is loud: your agent gets an `authentication_required` error with a payment intent object. You know exactly what happened. You can route around it, log it, notify a human, and continue other work.

Auth0's failure is silent: tokens work until they don't, at 60 days, across every agent that cached them. You find out when nothing works and you don't know why.

**The score difference is 1.8 points. The operational difference is massive.**

This is what we mean by failure engineering: understanding not just *if* an API fails, but *how* it fails, *when* you'll know, and *what state you're left in*.

We've mapped six failure categories that cover >95% of the agent-API failures we've seen across 1,038 scored services.

---

## The Six Failure Categories

### 1. Authentication Failures

**What breaks:** Token expiry, credential rotation, scope changes, multi-tenant isolation.

Authentication failures are the highest-impact category because they affect every subsequent request. One failed auth check can cascade to an entire fleet.

**Failure signatures by API:**

**Anthropic (8.4/10):** API key-based auth with no expiry. Failure mode: key revoked without agent awareness. Detection: 401 with `authentication_error` type and explicit message. Recovery cost: low — swap key, retry. Blast radius: one agent, not fleet.

**Auth0 (6.3/10):** Machine-to-machine tokens, 60-day default expiry. Silent expiry window — no webhook, no countdown endpoint, no renewal signal. Detection: 401 on first post-expiry request. Recovery cost: moderate (token refresh cycle). Blast radius: all agents sharing the token pool.

**Salesforce (4.8/10):** OAuth 2.0 session tokens with platform-specific expiry rules. Connected App configuration determines token lifetime, but limits vary by org configuration. An agent operating in one Salesforce org may behave differently in another. Detection: 401 with INVALID_SESSION_ID, but the session could be invalid for 5 different reasons.

**What to build:**
- Proactive token expiry monitoring (check expiry_at metadata, not just failure response)
- Per-agent credential scoping so a rotated token affects one agent, not the fleet
- Auth failure circuit breaker: after 2-3 consecutive 401s, halt agent and alert

**The key metric:** Does the API surface expiry time before expiry? Stripe gives you `expires_at` on restricted keys. Auth0 requires you to decode the JWT and parse `exp` yourself. That's the difference between proactive rotation and reactive scramble.

---

### 2. Rate Limit Failures

**What breaks:** Per-method limits, global limits, burst windows, shared quota pools.

Rate limit failures are the most common agent failure mode and the most preventable — if the API gives you enough information.

**The three rate limit failure patterns:**

**Pattern A — Hard stop with clear signal (best):**
API returns 429 with `Retry-After` header and specific limit type. Agent pauses exactly as long as needed, resumes. Zero state corruption.

*Example: Twilio (8.0/10)* — Returns 429 with rate limit context. The 1-second and 1-minute windows are documented and machine-readable. Agents can implement precise backoff.

**Pattern B — Hard stop, vague signal (acceptable):**
API returns 429 but without specific wait time. Agent must exponential-backoff and guess.

*Example: Shopify (7.8/10)* — GraphQL uses a cost budget system (not request count). Requests return `extensions.cost.throttleStatus` in the response body, not just headers. Agents need to parse response body to understand remaining budget — unusual pattern that breaks naive retry logic.

**Pattern C — Quota depletion without warning (worst):**
API silently drops requests or returns success responses when quota is exhausted. Agent thinks work is complete. Nothing was done.

*Example: HubSpot (4.6/10)* — Daily API call limits by tier. At limit, returns 429, but contact creation calls that hit a secondary daily limit can return 200 with empty body. No `Retry-After`. Agent logs "success."

**What to build:**
- Parse rate limit headers on every response, not just 429s
- Track quota consumption at the orchestration layer (not per-agent)
- Distinguish per-method limits from global limits — some APIs let you burn one method without affecting others
- Set 80% quota threshold alerts, not 100% — reactive rate limit handling is too late

---

### 3. State and Consistency Failures

**What breaks:** Object versioning, eventual consistency windows, concurrent writes, missing idempotency.

State failures are insidious because they often succeed. The request completes. The response is 200. But the world is different from what the agent believes.

**Three state failure patterns:**

**Pattern A — Missing idempotency (data duplication):**
Agent sends a create request. Network times out before response arrives. Agent retries. Two records created. No way to know.

*Stripe (8.1/10) vs. HubSpot (4.6/10)*: Stripe requires you to pass `idempotency_key` on every write. The same key always returns the same result. HubSpot has idempotency on some endpoints but not others — and which ones isn't clearly documented. A contact creation with the same email address creates a duplicate, not an error.

**Pattern B — Eventual consistency windows:**
Supabase/PostgreSQL is strongly consistent. But `Supabase (7.5/10)` RLS (Row Level Security) policies enforce on read, not write. An agent can write a row and immediately query for it — and get an empty result set because the RLS policy hasn't evaluated to true yet for the querying session. No error. Empty result. Agent proceeds as if the record doesn't exist.

**Pattern C — Object versioning conflicts:**
APIs that require version tokens on update (`If-Match` headers, `version` fields) will 412 if your agent has a stale version. This is correct behavior — but if the agent doesn't handle 412, it either fails loudly or retries with the stale version, creating a loop.

*Linear (7.8/10)*: GraphQL mutations require current version for conflict detection. Clean pattern once you understand it. Jira (7.5/10): optimistic locking via `version` field, but handling varies by endpoint — some endpoints silently overwrite.

**What to build:**
- Idempotency keys on all write operations (generate from job ID + operation type)
- Read-after-write verification for critical state (confirm the write before proceeding)
- Version token caching at the orchestration layer — fetch current version before write, not from cached state

---

### 4. Network and Availability Failures

**What breaks:** Timeouts, partial success, regional variance, infrastructure flakiness.

Most agents handle the happy path and the obvious failure. Network failures are neither — they're ambiguous.

**The ambiguous failure problem:**

A request to create a charge in Stripe takes 8 seconds. Your timeout is 10 seconds. At 9 seconds, the connection drops. Did the charge succeed?

This is the "timed out after success" failure mode. The server processed the request. The client never got the response. Without idempotency keys, the agent will create a duplicate charge on retry.

**Timeout failure signatures by category:**

| API | Timeout Behavior | Idempotency on Timeout | Agent Impact |
|-----|-----------------|----------------------|--------------|
| Stripe (8.1) | Fast-fail on auth, slower on charge | ✅ Full idempotency | Low — retry is safe |
| Twilio (8.0) | SMS delivery is async by default | ✅ Prevent duplicates | Low — separate send from delivery |
| SendGrid (6.35) | Variable by plan tier | ⚠️ Partial | Medium — email sends may duplicate |
| HubSpot (4.6) | Not documented per-endpoint | ❌ None documented | High — retry logic is a gamble |

**Partial success modes:**

Batch APIs can return 207 Multi-Status — some operations succeeded, some failed. An agent that only checks the top-level status code sees "200 OK" and marks the whole batch as complete. The failed items are never retried.

*Example: Google AI (8.3/10)* batch embedding requests: Returns top-level 200 even if individual embeddings failed with per-item error objects. Parse the response body item by item, not just the status code.

**What to build:**
- Timeout values per API endpoint, not global (charge creation needs 30s; health check needs 2s)
- Always use idempotency keys before timeouts happen (not after)
- Parse 207 Multi-Status response bodies — never assume all-success from HTTP 200
- Regional failover logic for APIs with documented regional outages (check status.stripe.com, not just 5xx)

---

### 5. Silent Failures

**What breaks:** Requests that appear to succeed but don't do anything. The worst failure mode.

A silent failure is a request that returns 200 but the intended effect never happened. Agents can't detect these from response codes alone.

**Silent failure patterns we've observed:**

**Quota enforcement via 200:** Some APIs return 200 when quota is exhausted but silently drop the request. The response body looks normal. Nothing was sent, stored, or processed.

**Truncation without signal:** APIs that accept text payloads often have hidden character limits. HubSpot (4.6) note fields accept text but silently truncate at undocumented lengths. The agent stores 10,000 characters, the API stores 2,000, the field value on read is shorter than what was written.

**Validation that accepts invalid input:** Loose schema validation can accept a request, store it, and return 200 — but the stored object is malformed in a way that causes downstream failures. Classic: storing `null` where you meant to store an empty array `[]`. The object was created. It's unusable.

**Webhook events that don't fire:** APIs with event systems often have undocumented conditions where webhooks don't fire. Salesforce (4.8) change data capture has processing delays under load. Agents that rely on webhooks for state confirmation can wait indefinitely.

**What to build:**
- Read-after-write verification for critical state transitions (especially for APIs below 7.0)
- Character count assertions before writing to known-truncating APIs
- Webhook heartbeat monitors — verify events are flowing, not just that subscriptions exist
- Negative confirmation patterns: "I wrote X, I will now read back X and verify"

---

### 6. Observability Failures

**What breaks:** Missing audit logs, inconsistent error messages, no webhook coverage, API changelog lag.

When something goes wrong in a fleet, you need to answer: what happened, when, and to which agent? Observability failures make this impossible.

**Low vs. high observability APIs:**

**High observability — Stripe (8.1):**
- Every API request logged with request ID, timestamp, source IP
- Errors include `charge_id` in every response for cross-reference
- Webhook events map directly to API calls (one-to-one traceability)
- Dashboard shows real-time API usage, error rates, and dispute events
- `Stripe-Request-Id` header enables exact correlation to Stripe logs

**Low observability — HubSpot (4.6):**
- Property history tracked, but API error history is limited
- No native request ID on errors (must add your own correlation)
- Webhook delivery logs not exposed via API — must check dashboard manually
- Rate limit headers inconsistent across API versions
- Property change history not always available in API response

**The key observability markers:**
1. Does every response include a request ID you can use for correlation?
2. Are webhook delivery failures exposed programmatically?
3. Is the audit log (not just the data) queryable via API?
4. Do error messages include enough context to reproduce the failure?

**What to build:**
- Log request IDs from every API call, not just failures
- Synthetic monitoring: run known test operations on a schedule and verify expected outcomes
- Error fingerprinting: hash error messages to detect new failure modes vs. recurring patterns

---

## Failure Recoverability Matrix

Not all failures are equal. This 2x2 maps detectability × reversibility across 20 APIs in our portfolio:

**High detectability + Reversible (best):**
Stripe SCA/3DS trigger, Twilio A2P 10DLC, Shopify GraphQL cost budget, Linear version conflicts. These fail loudly, return machine-readable errors, and can be retried or routed around.

**High detectability + Irreversible (plan ahead):**
Stripe SCA human redirect, Salesforce governor limits (one-time quota burn). You'll know, but you can't undo it. Design your agents to halt, not retry.

**Low detectability + Reversible (monitor actively):**
Auth0 token expiry, Supabase RLS eventual consistency, SendGrid delivery variance. Failures are silent until they're obvious. Build proactive monitoring.

**Low detectability + Irreversible (highest risk):**
HubSpot silent truncation, Salesforce sandbox/production state splits, quota enforcement via 200. This is the zone where your agents can silently corrupt production state.

The practical implication: **API selection for autonomous agents should weight detectability and reversibility, not just performance**.

An agent fleet that runs overnight at 3am cannot tolerate low-detectability failures. If something goes wrong and you don't find out until morning, the blast radius is 8 hours of unchecked state.

---

## How AN Score Captures Failure Recoverability

The AN Score execution dimension (which carries ~70% of the total score) is where failure mode data lives.

**What we measure:**
- **Error quality:** Are errors machine-readable? Do they include type, code, and context?
- **Rate limit transparency:** Are limits surfaced before they're hit? Are wait times explicit?
- **Idempotency coverage:** Which operations have idempotency guarantees?
- **Retry semantics:** Does the API tell you what's safe to retry and what isn't?
- **Audit surface:** Can you reconstruct what happened via the API?

The spread in execution scores is wide:
- Anthropic: 8.4 — structured errors, predictable behavior, explicit rate limit metadata
- Twilio: 8.0 — idempotency on sends, clear delivery status, actionable errors
- Google AI: 8.3 — strong error structure, but batch response parsing requires care
- Auth0: 6.3 — silent token expiry, inconsistent error formats across grant types
- HubSpot: 4.6 — silent quota enforcement, truncation without signal, legacy API version divergence

For fleet operators running agents overnight: filter your API portfolio by execution score first. An API with execution > 7.5 has the failure signatures you can build around. Below 6.0, you need human-in-the-loop checkpoints.

---

## Telemetry You Need for Each Failure Category

**Auth failures:**
- Log every 401/403 with timestamp, API, request ID, and agent ID
- Monitor token expiry windows proactively (check `exp` claim daily)
- Alert on: consecutive auth failures from the same agent (fleet credential issue)

**Rate limit failures:**
- Log rate limit headers on every response (not just 429s)
- Track quota consumption rate per API per hour
- Alert on: >80% quota consumed before work is expected to complete

**State/consistency failures:**
- Log idempotency keys used per job
- Run read-after-write on critical operations (sample 10%, not 100%)
- Alert on: read-after-write mismatches (indicates write didn't commit as expected)

**Network/availability failures:**
- Separate timeout metrics by endpoint (charge creation != health check)
- Log request duration percentiles per API
- Alert on: p99 latency exceeding your timeout threshold (impending timeout failures)

**Silent failures:**
- Run synthetic test operations on a schedule (small known-state writes)
- Verify response body structure, not just status code
- Alert on: anything that diverges from expected response schema

**Observability failures:**
- Ensure request IDs are logged for every API call
- Test webhook delivery on your staging environment before production
- Alert on: webhook silence for >30 minutes on active APIs

---

## Failure Engineering Checklist for New API Integrations

Before adding any new API to an autonomous agent fleet:

```plaintext
□ Auth model documented: key type, expiry window, rotation endpoint exists?
□ Rate limits documented: per-method or global? Headers on all responses?
□ Idempotency: does the API support idempotency keys? On which operations?
□ Error quality: do errors include type + code + context? Machine-readable?
□ Batch behavior: does the API return 207 or per-item errors?
□ Webhook coverage: which operations fire webhooks? Are missed deliveries detectable?
□ Silent failure modes: any known truncation, quota enforcement via 200, or validation gaps?
□ Observability: request ID on responses? Audit log queryable via API?
□ Recovery cost: what's the blast radius if this integration fails overnight?
□ AN Score: execution dimension > 7.0 for overnight autonomous operation
```

---

## The Series, Summarized

Five articles in, the pattern is clear:

**Choose APIs by how they fail, not just how they perform.**

The agent infrastructure stack — LLM API → agent loop → rate limit architecture → credentials management → failure engineering — is a set of interlocking reliability problems. Each layer amplifies failures from the layer below.

A silent auth failure in your credentials layer creates ghost agents running on expired tokens. Those agents hit rate limits at unpredictable times (because they're retrying failed requests). The rate limit failures produce ambiguous state. The ambiguous state is undetectable without observability instrumentation.

Everything connects. This is why the execution dimension carries 70% of AN Score weight: production reliability is what separates APIs that work from APIs that work *autonomously*.

---

**Rhumb AN Score** scores 1,038 services across 20 dimensions. [Find the right APIs for your agent stack →](https://rhumb.dev/leaderboard)

---

## Agent Infrastructure Series

**New:** [The Complete Guide to API Selection for AI Agents (2026)](/blog/complete-guide-api-selection-for-ai-agents) — one-page hub linking every Rhumb article and the full agent infrastructure stack.

This article is part of a 5-part series on production agent infrastructure:

- **Part 1:** [LLM APIs for AI Agents](/blog/anthropic-vs-openai-vs-google-ai)
- **Part 2:** [LLM APIs in Agent Loops](/blog/llm-apis-agent-loops)
- **Part 3:** [Designing Agent Fleets That Survive Rate Limits](/blog/agent-fleet-rate-limit-design)
- **Part 4:** [API Credentials in Autonomous Agent Fleets](/blog/api-credentials-agent-fleets)
- **Part 5:** [How APIs Fail When Agents Use Them](/blog/api-failure-modes-engineering)

---

*Part 5 of 5: Agent Infrastructure Series. Parts 1-4 cover LLM API selection, agent loop behavior, rate limit fleet architecture, and credentials management.*
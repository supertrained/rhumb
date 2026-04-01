# AUD-R1-03 — DB-Down Control-Plane Posture Design

**Date:** 2026-04-01  
**Scope:** Resolve v2 / hot-path control-plane behavior during Supabase outage or partial DB degradation  
**Verdict:** Rhumb should stop treating DB outage as a generic “best effort” problem. The hot path needs an explicit split:

- **Financial uniqueness / operator-control surfaces:** **FAIL_CLOSED**
- **Abuse throttles:** **DEGRADED_BUT_SAFE**
- **Observability / audit persistence:** **DEGRADED_BUT_SAFE**, but only with a real durable outbox; otherwise it is not safe enough to claim degraded operation
- **No hot-path financial control should be FAIL_OPEN**

---

## Executive Position

The current system degrades **independently** at multiple layers:

- durable rate limits fall back to process memory
- replay prevention falls back to process memory
- idempotency either fails open or is only in-memory
- kill-switch durability falls back to in-memory / empty-on-restart state
- billing and audit persistence are best-effort

That is survivable **one control at a time**. It is **not** survivable as a coordinated outage posture. During a Supabase incident — especially if combined with a deploy, restart, or multi-worker traffic — those fallbacks can align into a practical **control-plane fail-open**.

### Recommended design principle

**If a control decides whether Rhumb may spend money, accept money, execute a side effect, or honor an operator kill decision, that control must not silently degrade to weaker semantics.**

More concretely:

1. **Money safety beats UX.** If Rhumb cannot durably prove a payment proof is single-use, do not execute.
2. **Operator control beats availability.** If kill-switch authority cannot be trusted, block risky execution.
3. **Auditability can degrade only via durable buffering.** “Log and continue” is acceptable only if logs are written to a local durable outbox that survives restart.
4. **Abuse throttles may degrade locally** if they remain conservative and are not the only thing preventing financial harm.

---

## Hot-Path Surface Map

### 1) Rate limits
Affected code:

- `packages/api/services/durable_rate_limit.py`
- `packages/api/middleware/rate_limit.py`
- `packages/api/routes/capability_execute.py`

Current hot-path uses:

- per-IP middleware throttling
- per-agent execution rate limit
- per-agent managed daily cap
- per-wallet x402 anonymous limit

### 2) x402 replay / payment single-use
Affected code:

- `packages/api/services/durable_replay_guard.py`
- `packages/api/routes/capability_execute.py`
- `usdc_receipts` insert path inside `capability_execute`

Current hot-path uses:

- durable replay claim for legacy `tx_hash` path
- historical check against `usdc_receipts`
- standard x402 authorization flow appears to rely on settlement + receipt insertion, not the same replay-guard path

### 3) Idempotency
Affected code:

- `packages/api/services/durable_idempotency.py`
- `packages/api/services/recipe_safety.py`
- `packages/api/routes/capability_execute.py`
- `packages/api/routes/recipes_v2.py`

Current hot-path uses:

- `capability_execute`: best-effort lookup in `capability_executions`; if DB read fails, execution proceeds
- `recipes_v2`: in-memory recipe idempotency only
- durable idempotency store exists but is not the enforced hot-path authority

### 4) Kill switches
Affected code:

- `packages/api/services/kill_switches.py`
- `packages/api/services/durable_event_persistence.py`
- `packages/api/routes/capability_execute.py`
- `packages/api/routes/recipes_v2.py`
- `packages/api/app.py`

Current hot-path uses:

- env-based coarse switches (`MANAGED_EXECUTION_ENABLED`, `MANAGED_ONLY_KILL`)
- fine-grained kill-switch registry with optional durable load/persist
- registry falls back to in-memory if durable init fails

### 5) Billing / audit persistence
Affected code:

- `packages/api/services/durable_event_persistence.py`
- `packages/api/services/billing_events.py`
- `packages/api/services/audit_trail.py`
- `packages/api/routes/resolve_v2.py`
- `packages/api/routes/providers_v2.py`
- `packages/api/routes/capability_execute.py`
- `packages/api/routes/recipes_v2.py`

Current hot-path uses:

- `billing_events` and `audit_trail` are in-memory services
- durable event persistence adapters exist but are not the authoritative write path for those services
- several DB writes in execute paths are best-effort or have return values ignored
- recipe execution persistence is not treated as a hard prerequisite

### 6) Recipe execution safety
Affected code:

- `packages/api/routes/recipes_v2.py`
- `packages/api/services/recipe_safety.py`
- internal forwarding to `resolve_v2` / `capability_execute`

Current hot-path uses:

- recipe definition fetched from Supabase at execution time
- recipe execution persistence written after execution, but failure is not enforced
- recipe idempotency is process-local only
- recipe steps inherit Layer 2/Layer 1 execution behavior underneath

---

## Policy Table

| Surface | Current behavior | Recommended behavior | Rationale | Implementation notes |
|---|---|---|---|---|
| Rate limits | `DurableRateLimiter` falls back to in-memory on DB/RPC errors. Middleware also falls back to in-memory if durable init fails. Cross-worker guarantees disappear; restart resets counters. | **DEGRADED_BUT_SAFE** | **Abuse resistance + UX.** Rate limits protect against flooding, but they are not the final financial integrity control. Rhumb can continue with stricter local throttles if stronger financial controls fail closed. | Keep an explicit **DB-down emergency limiter** with lower caps for execute paths, especially anonymous/x402 and managed execution. Emit a control-plane degraded metric/header. Do **not** describe local fallback as equivalent protection. |
| x402 replay / payment single-use | Legacy tx-hash path uses `DurableReplayGuard`, but DB failure falls back to in-memory. Historical check also consults `usdc_receipts`. Standard authorization flow is not obviously using the same replay-claim guard. | **FAIL_CLOSED** | **Financial safety.** If Rhumb cannot durably prove a payment proof is unused, it must not execute. Replaying a valid payment is a direct loss event. | Remove in-memory fallback for payment authorization. Require a durable claim on the payment identity before execution. Unify legacy tx-hash and standard authorization flows under the same single-use authority. If claim/store fails, return `503 payment_protection_unavailable`. |
| Idempotency | `durable_idempotency.py` is fail-open by design and appears unused on the hot path. `capability_execute` does a best-effort DB read only. `recipes_v2` uses in-memory idempotency. | **FAIL_CLOSED** | **Financial safety + user trust.** Idempotency exists specifically to prevent duplicate execution/charges. Ignoring it during DB outage defeats its purpose at the moment it matters most. | Make durable claim-before-execute mandatory for billable or side-effecting operations. For recipes, either require caller idempotency keys or generate a deterministic server-side key from recipe+inputs+agent. If durable idempotency is unavailable, reject execution with a precise 503 instead of proceeding. |
| Kill switches | Fine-grained kill-switch state is loaded from durable persistence when available, but init failure falls back to in-memory registry. Persist/remove failures are logged only. After restart during DB outage, registry can come up empty and effectively treat “unknown” as “not killed.” | **FAIL_CLOSED** | **Operator control integrity.** A kill switch is an override against harm. If Rhumb cannot establish authoritative kill state, it must not assume the system is clear to execute. | Treat kill-switch availability as a gating prerequisite for risky execution surfaces. Preserve env-based coarse kills as independent backstops. Add a last-known-good signed snapshot only if it has explicit freshness bounds; otherwise block execute/recipe routes when kill authority is unavailable. |
| Billing / audit event persistence | Durable persistence adapters are best-effort and largely disconnected from the core in-memory `billing_events` / `audit_trail` services. Some hot-path inserts are best-effort or unchecked. | **DEGRADED_BUT_SAFE** | **Auditability + launch defensibility.** Billing/audit telemetry should not disappear silently, but it also should not be the first thing that takes the service down if a safe buffer exists. | Replace “log and continue” with a **local durable outbox/WAL** that survives restart. Flush asynchronously to Supabase when healthy. If the outbox is unavailable or backlog exceeds a threshold, escalate to `FAIL_CLOSED` for billable execution and kill-switch mutations. |
| Recipe execution safety | Recipe execution depends on DB for published recipe lookup, auth context, and downstream execution metadata, but durable idempotency is absent and execution persistence is not enforced. DB outage can surface as misleading not-found or partial/no-record execution. | **FAIL_CLOSED** | **Financial safety + operator honesty.** Recipes amplify cost and side effects through multiple steps. Running them without durable control state is not defensible. | If recipe definition fetch, durable idempotency claim, or durable execution record path is unavailable, reject execution cleanly with `503 recipe_control_plane_unavailable`. Allow only read-only introspection if desired. |

---

## Surface-by-Surface Principles

### Rate limits → DEGRADED_BUT_SAFE
Rate limiting is an **abuse** control, not a proof-of-payment control. It is acceptable to degrade to local, stricter throttles during DB outage **only if**:

- anonymous and managed paths become more conservative, not less
- billing/replay/idempotency controls do **not** also fail open
- operators can see the degraded state immediately

This is the only major hot-path surface where degraded execution is defensible.

### x402 replay → FAIL_CLOSED
Replay prevention is not a nice-to-have. It is the control that keeps “one payment” from becoming “N executions.” The current in-memory fallback is acceptable for test/dev ergonomics, not for production financial safety.

Recommended production rule:

> No durable replay claim, no paid execution.

### Idempotency → FAIL_CLOSED
The current design comment in `durable_idempotency.py` (“better to risk a duplicate than block all executions”) is exactly the wrong tradeoff for billable or externally side-effecting work.

For launch-defensible behavior, the correct rule is:

> If a request presents itself as retry-safe, Rhumb must either honor that guarantee durably or reject the request.

### Kill switches → FAIL_CLOSED
Kill switches are the last operator override. “DB unavailable” must not be interpreted as “safe to proceed.” The current registry fallback is especially dangerous on restart, because a live worker may still have a local in-memory kill state while a fresh worker starts empty.

That is a classic split-brain control failure.

### Billing / audit persistence → DEGRADED_BUT_SAFE
Auditability matters, but there is an important distinction:

- **Silent drop:** unacceptable
- **Durable local buffering:** acceptable for bounded periods
- **Continue forever without durable audit trail:** unacceptable

So this surface is degraded-but-safe **only after** Rhumb has a real outbox. Until then, current behavior is better described as “best effort,” not safe degradation.

### Recipes → FAIL_CLOSED
Recipes multiply risk because they fan out across steps, providers, and billing events. They should be the **strictest** path, not the loosest. If the control plane is uncertain, recipe execution should stop.

---

## Key Inconsistencies and Coupled-Failure Risks

### 1) Coordinated fallback creates a practical fail-open path
Individually, each fallback looks survivable. Together, they are not.

Example failure chain:

1. Supabase becomes partially unavailable
2. rate limits fall back to local memory
3. replay guard falls back to local memory
4. idempotency read misses or fails open
5. event persistence silently drops
6. a worker restarts and loses in-memory kill-switch / replay / idempotency state

That is exactly the condition under which abuse, duplicate payment use, and un-auditable execution can co-occur.

### 2) Split-brain across workers/processes
Process-local fallback is not a control-plane substitute.

During outage, different workers can disagree about:

- whether a tx hash was already used
- whether an idempotency key was already claimed
- whether a kill switch is active
- how much rate-limit budget remains

That means the system becomes nondeterministic under load — the opposite of what a control plane should be.

### 3) Cold-start amnesia for kill switches
`init_kill_switch_registry()` falls back to in-memory on durable init failure. On a fresh boot during DB outage, that can erase all fine-grained operator control from the perspective of that worker.

This is the highest-integrity concern after payment replay.

### 4) Idempotency policy is inconsistent across layers
- `capability_execute` has best-effort DB lookup semantics
- `recipes_v2` has in-memory-only semantics
- `durable_idempotency.py` exists but is fail-open and apparently not authoritative

This is a design smell: the same concept has three different outage behaviors.

### 5) Standard x402 path and legacy tx-hash path are asymmetric
Legacy tx-hash flow clearly invokes the replay guard. Standard authorization flow appears to rely on settlement and receipt insertion without the same explicit durable claim step.

Even if settlement path currently prevents duplicate settlement in practice, the policy is inconsistent and should be unified.

### 6) Current recipe outage behavior is not honest enough
A DB outage on recipe definition fetch can surface as “recipe not found,” which is operationally misleading. A control-plane outage should return a control-plane error, not pretend the resource vanished.

### 7) Billing/audit durability is over-claimed relative to actual wiring
The durable persistence module exists, but the primary billing/audit services are still in-memory singletons. That means the architecture implies durability that the runtime path does not actually guarantee.

---

## Recommended Implementation Sequence

### 1) Establish one shared outage policy primitive
Create a single control-plane availability module for hot-path decisions.

It should answer questions like:

- can we durably claim payment uniqueness?
- can we durably claim idempotency?
- can we load authoritative kill-switch state?
- is the durable event outbox writable?

Do **not** let each service invent its own fallback semantics.

### 2) Make payment replay protection fail closed first
This is the most urgent change.

- remove in-memory fallback from production payment authorization
- require durable single-use claim before executing paid work
- unify legacy tx-hash and standard x402 authorization paths under the same policy
- return a precise 503 when payment integrity cannot be guaranteed

### 3) Make idempotency fail closed for execute + recipes
Second priority.

- move `capability_execute` to durable claim-before-execute semantics
- wire recipes to the durable store
- stop treating DB read failure as “no idempotency hit”
- require or derive deterministic keys for recipe execution

### 4) Make kill-switch authority explicit and authoritative
Third priority.

- do not interpret durable load failure as “no active kill switches”
- block risky execution if no authoritative kill state is available
- keep env-based nuclear switches independent
- optionally persist a signed, freshness-bounded last-known-good snapshot for restart continuity

### 5) Add a real durable outbox for billing/audit persistence
Fourth priority.

- local append-only outbox/WAL on the API host/container
- async flush to Supabase when available
- metrics for backlog age/size
- hard cutoff: if outbox fails or backlog exceeds threshold, stop billable execution

### 6) Reframe rate-limit fallback as emergency mode, not equivalence
Fifth priority.

- keep local throttles, but tighten them during DB-down mode
- especially tighten x402 anonymous and managed execution paths
- emit explicit observability so operators know the system is degraded

### 7) Fix error honesty on DB-dependent recipe/control paths
Sixth priority.

- replace false 404-style behavior with `503 control_plane_unavailable`
- distinguish resource absence from DB unavailability
- document this in API error contracts

### 8) Add outage / restart / split-brain tests
Final priority, but required before calling this complete.

Test matrix should include:

- DB down before process boot
- DB down after warm boot
- one worker restarted during outage
- legacy x402 path under outage
- standard x402 path under outage
- recipe execution under outage
- outbox full / unwritable
- kill switch activated before outage, then restart during outage

---

## Bottom Line

Rhumb needs a **deliberate asymmetric posture** during DB outage:

- **Fail closed** for anything that protects money, uniqueness, or operator authority
- **Degrade safely** only for throttling and telemetry, and only when the degraded mode is explicitly bounded and observable
- **Never silently substitute process-local memory for durable financial control semantics**

That is the posture most likely to survive real incidents, adversarial review, and launch scrutiny.

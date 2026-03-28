# Emailable execution slice — 2026-03-28

Owner: Pedro
Status: shipped in product main as the next blocked-safe execution wedge

## Why this lane now

The live priority stack still starts with:
1. x402 buyer → settle → execute proof
2. Airship controlled internal proof

But both were blocked in this loop:
- **x402 live proof** is still gated by recovering the funded Awal buyer wallet identity and a safe restart path for the hung local process.
- **Airship proof** is blocked more concretely than before: `RHUMB_CREDENTIAL_AIRSHIP_BASIC_AUTH` is not present in the current execution environment, so even validation-only proof cannot run honestly from this lane.

That made **Emailable** the correct next unblocked move.

## What shipped

### Managed execution wiring
- `email.verify` → `GET /v1/verify`
- `email.batch_verify` → `POST /v1/batch`

### Honest Phase 0 contract
- `email.verify` returns Emailable's real verification payload.
- `email.batch_verify` only claims **batch accepted / batch created** semantics.
- The batch slice does **not** pretend that batch results are synchronously available.

### Input normalization
The Rhumb-managed executor now accepts logical Rhumb-style inputs and translates them into Emailable-native parameters:
- `email_address` → `email`
- `emails: []` → comma-separated `emails`
- `callback_url` / `webhook_url` → `url`
- `response_fields: []` → comma-separated `response_fields`
- `smtp_check` → `smtp`
- `accept_all_check` → `accept_all`
- `max_wait_seconds` → `timeout`

## Why Emailable is a good wedge

The API surface is unusually clean for this category:
- single-address verification is explicit and low-risk
- auth is simple and standard
- test keys exist, which matters for honest future runtime verification
- batch creation is explicit enough to support later status polling without inventing fake abstractions

## Important honesty rule

Batch verification is **not** modeled as “results returned immediately.”

For Emailable today:
- `email.batch_verify` means **start a batch job and return its identifier / provider response**
- follow-up polling is a separate concern and should be added as its own status/read slice, not smuggled into the create call

That keeps Resolve truthful instead of flattening an async provider into a fake synchronous contract.

## What did not ship

- No runtime-backed public review yet
- No batch-status capability yet
- No production proof yet, because the managed credential is not present in this environment

## Recommended next move from here

1. If the Emailable credential becomes available, run a validation pass on `email.verify` first using a test key or low-risk test address.
2. Then run a small `email.batch_verify` proof to confirm batch creation semantics and response shape.
3. If the provider control path is clean, publish the runtime-backed evidence and review.

## Net

**Airship was blocked, so the loop advanced the next honest wedge instead.**

Rhumb now has a concrete execution slice for the strongest email-validation provider in the newly expanded category, without overclaiming synchronous batch semantics.

# Phase 3 runtime review — Stripe

Date: 2026-03-26
Owner: Pedro / Keel runtime review loop
Priority: Phase 3 callable-provider verification

## Why Stripe

Google AI is still not live in the callable inventory, so the next unblocked lane remained callable-provider runtime review depth.

Stripe was the cleanest BYOK target because:
- it is already listed as callable in production status
- it exposes a safe, non-mutating read path (`GET /v1/account`)
- direct-control parity is easy to verify with the same test credential
- it avoids Twilio lookup spend and avoids Slack message-send side effects

## Setup note

The stored launch dashboard key was not suitable for this verification path because its backing agent had **zero service grants**. The first proxy attempt returned:
- `403 forbidden`
- detail: `Agent '<id>' has no access to service 'stripe'`

Rather than mutating the launch/dashboard agent, I used the same pattern as the Tavily rerun:
- create a fresh internal runtime-review agent
- grant it **only** Stripe access
- run the verification through that scoped agent key

This isolates the runtime proof from unrelated dashboard-state drift.

## Test setup

### Rhumb proxy execution
- Endpoint: `POST /v1/proxy/`
- Service: `stripe`
- Method/path: `GET /v1/account`
- Agent: ephemeral runtime-review agent `2379ce7d-ad32-41c9-ab52-815d6a71420f`
- Result target:
  - account id
  - country

### Direct provider control
- Endpoint: `GET https://api.stripe.com/v1/account`
- Auth: direct Stripe test secret key
- Result target:
  - account id
  - country

## Results

### Rhumb proxy
- Result: **succeeded**
- HTTP status: **200**
- Response highlights:
  - `id: acct_1Sikl52H0xSyjdgP`
  - `country: US`

### Direct Stripe control
- Result: **succeeded**
- HTTP status: **200**
- Response highlights:
  - `id: acct_1Sikl52H0xSyjdgP`
  - `country: US`

## Comparison

| Dimension | Rhumb proxy | Direct Stripe |
|---|---|---|
| Reachability | Healthy | Healthy |
| Auth path | Rhumb proxy credential injection | Direct Stripe test secret key |
| Output | Account id + country returned | Same account id + country returned |
| Side effects | None | None |
| Operator conclusion | Working production Stripe proxy path | Provider API healthy |

## Public trust surface update

After the live rerun:
- a new `runtime_verified` evidence record was inserted for Stripe
- a new published review was created: **"Stripe: Phase 3 runtime check passes on non-mutating account read"**
- the review was linked to the evidence record in `review_evidence_links`

Review id:
- `0c95fc26-1784-4606-97d6-0c315e5ff0f3`

Evidence id:
- `6ca19287-eea8-49c3-ae31-1f7903dedfa0`

## Phase 3 verdict

**Stripe is Phase-3-verified in production.**

The current Stripe proxy/auth path cleanly matches direct provider control on a safe read-only check.

## Follow-up

1. Continue the next BYOK runtime review while Google AI remains absent from the live callable inventory.
2. Slack and Twilio remain the active BYOK verification backlog.
3. Keep the launch/dashboard agent grant gap in view as a separate UX/bootstrap concern, but do not block runtime-review progress on it.

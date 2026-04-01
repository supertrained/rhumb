# Stripe current-depth4 runtime review — 2026-03-31

Date: 2026-03-31
Owner: Pedro / Keel runtime review loop
Priority: Callable freshness rotation

## Why Stripe

I re-read the live public callable coverage audit before touching the next lane.

Pre-pass artifact:
- `rhumb/artifacts/callable-review-coverage-2026-03-31-pre-stripe-depth4.json`

Live truth before the pass:
- weakest claim-safe callable depth: **3**
- weakest bucket: `slack`, `stripe`, `github`, `twilio`, `algolia`
- **Stripe** was the stalest provider in that bucket by freshest runtime evidence timestamp:
  - Stripe freshest runtime evidence: `2026-03-26T15:42:54.647306Z`
  - Slack freshest runtime evidence: `2026-03-26T17:48:45.453016Z`
  - Algolia freshest runtime evidence: `2026-03-30T20:44:08Z`
  - Twilio freshest runtime evidence: `2026-03-31T23:28:16Z`
  - GitHub freshest runtime evidence: `2026-04-01T00:23:34Z`

So the next honest freshness target was **Stripe**, not a reopen of dogfood or Google AI.

## What shipped

Added reusable helper:
- `rhumb/scripts/runtime_review_stripe_depth4_20260331.py`

Design notes:
- uses the safe non-mutating Stripe read path `GET /v1/account`
- runs the Rhumb side through the live proxy surface (`POST /v1/proxy/`)
- compares against direct Stripe control
- is **env-first with 1Password fallback** for the direct credential path:
  - first checks `RHUMB_CREDENTIAL_STRIPE_API_KEY`
  - falls back to `sop item get "Stripe Test Secret Key (Rhumb)" --vault "OpenClaw Agents" --fields credential --reveal`

## Runtime pass truth

Runtime artifact:
- `rhumb/artifacts/runtime-review-pass-20260401T021859Z-stripe-depth4.json`

Pass setup:
- temp org: `org_runtime_review_stripe_20260401t021859z`
- temp review agent: created + granted only `stripe`
- direct credential source used in this pass: **environment**

Rhumb proxy path:
- endpoint: `POST /v1/proxy/`
- service: `stripe`
- method/path: `GET /v1/account`

Direct control path:
- endpoint: `GET https://api.stripe.com/v1/account`

Managed vs direct parity passed exactly on:
- `id = acct_1Sikl52H0xSyjdgP`
- `country = US`
- `default_currency = usd`
- `charges_enabled = true`
- `payouts_enabled = true`
- `details_submitted = true`
- `business_type = company`
- `branding_icon = null`

Verdict:
- Rhumb proxy envelope status: **200**
- Rhumb upstream status: **200**
- direct Stripe status: **200**
- parity: **true**

## Publication truth

Publication artifact:
- `rhumb/artifacts/runtime-review-publication-2026-03-31-stripe-depth4.json`

Published trust rows:
- evidence: `3ec6db1e-1266-4e58-a0f1-7a5f5966bde8`
- review: `19aae77f-49c3-420b-9491-8a4be7c3ab5d`

Review summary published:
- safe account-read parity through Rhumb Resolve on the non-mutating `GET /v1/account` path

## Coverage impact

Post-pass artifact:
- `rhumb/artifacts/callable-review-coverage-2026-03-31-post-stripe-depth4.json`

Coverage result:
- `stripe` moved **3 → 4** claim-safe runtime-backed reviews
- weakest callable depth stayed **3**
- weakest bucket shrank from **5 providers → 4**
- remaining weakest providers:
  - `slack`
  - `github`
  - `twilio`
  - `algolia`

Next honest freshness target:
- **Slack** (now the stalest provider remaining in the depth-3 bucket)

## Operator conclusion

Stripe remains healthy on the safe read-only proxy path, and the public trust surface is now fresher and claim-safe at depth 4.

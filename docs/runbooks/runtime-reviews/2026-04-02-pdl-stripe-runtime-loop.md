# Runtime review loop — PDL fix verify + Stripe execute pass

Date: 2026-04-02
Owner: Pedro / Keel runtime review loop

## Mission 0 — PDL fix verification rerun

### Why this rerun happened
Commit `94c8df8` shipped a slug-normalization fix for **People Data Labs** (`people-data-labs` → proxy slug `pdl`). Mission 0 required a production rerun on the canonical Phase 3 path to confirm the fix actually worked live.

### Execution path
- Capability: `data.enrich_person`
- Provider: `people-data-labs`
- Credential mode: `rhumb_managed`
- Input: `profile=https://www.linkedin.com/in/satyanadella/`
- Rail: funded temp org + temp review agent + explicit service access grant

### Control test
Direct control hit:
- `GET https://api.peopledatalabs.com/v5/person/enrich?profile=...`
- Header: `X-Api-Key: RHUMB_CREDENTIAL_PDL_API_KEY`

### Result
- Rhumb estimate: **200**
- Rhumb execute: **200**
- Upstream provider status through Rhumb: **402**
- Direct provider control: **402**
- Error parity: **matched**
- `provider_used`: **people-data-labs**
- Verdict: **PASS**

### Interpretation
This is the expected post-fix outcome.
- The canonical slug now resolves correctly.
- Rhumb reaches the real PDL upstream.
- The live failure mode is provider quota / account limit, not execution-layer breakage.
- Since Rhumb and direct control returned the same provider error, the slug-normalization fix is confirmed live.

Artifact:
- `artifacts/runtime-review-pass-20260402T104620Z-pdl-fix-verify-20260401b.json`

## Mission 1 — Stripe current pass via execute route

### Why Stripe was chosen
Fresh public callable audit before the pass showed the weakest claim-safe callable bucket at **7** reviews:
- `slack`
- `stripe`
- `twilio`

PDL was skipped after Mission 0. Stripe was the stalest member of that weakest bucket, so it was the right next verification target.

### Execution path
- Capability: `wallet.get_balance`
- Provider: `stripe`
- Credential mode: `byo`
- Rhumb route: `POST /v1/capabilities/wallet.get_balance/execute`
- Upstream path executed through Resolve: `GET /v1/balance`

### Control test
Direct control hit:
- `GET https://api.stripe.com/v1/balance`
- Header: `Authorization: Bearer <Stripe test secret>`

### Comparison
Compared normalized fields:
- `object`
- `livemode`
- `available` (currency / amount / card source amount)
- `pending` (currency / amount / card source amount)
- `refund_and_dispute_prefunding` (available / pending)

### Result
- Rhumb estimate: **200**
- Rhumb execute: **200**
- Rhumb upstream status: **200**
- Direct provider control: **200**
- Field parity: **exact match**
- Verdict: **PASS**

### Public trust-surface effect
Post-pass public callable audit moved Stripe from **claim-safe depth 7 → 8**.

Artifacts:
- `artifacts/runtime-review-pass-20260402T105028Z-stripe-depth8.json`
- `artifacts/runtime-review-publication-2026-04-02-stripe-depth8.json`
- `artifacts/callable-review-coverage-2026-04-02-pre-current-pass-from-cron.json`
- `artifacts/callable-review-coverage-2026-04-02-post-stripe-current-pass-from-cron.json`

### Small tooling note
The one-off publish helper headline landed as "depth-5" because its local counter only counted `🟢 Runtime-verified` reviews and omitted `🧪 Tester-generated` rows. That underclaims rather than overclaims; the authoritative callable audit confirms Stripe's claim-safe depth is now **8**. The helper script was patched after the run so future depth labels count both runtime-backed trust labels.

## Mission 2 — Discovery expansion

Chose **identity** as the underrepresented high-demand category.

Why:
- live public category counts showed identity at only **4** providers
- agents constantly need read-first user / org / membership / session checks
- the catalog was missing several major commercial identity surfaces developers actually choose between

Added services:
- `auth0`
- `clerk`
- `stytch`
- `descope`
- `kinde`

Phase 0 recommendation:
- best first Resolve wedge: `identity.user.get`, `identity.user.list`, `identity.organization.members.list`
- best first provider target: **Clerk**

Shipped docs/migration:
- `packages/api/migrations/0148_identity_expansion.sql`
- `docs/runbooks/discovery-expansion/2026-04-02-identity-expansion.md`

## Net

This loop did what the SOP asked for:
- re-verified the shipped PDL slug fix on the live canonical path
- ran a real execute-route runtime pass plus direct control for the weakest stale callable provider
- expanded discovery in a genuinely underweight, high-demand category

# 2026-03-30 — Apollo current-depth freshness rerun (depth 4 → 5)

## Goal
Advance the next honest unblocked callable-review lane after the callable floor reached depth 4 across all providers.

At the start of this pass:
- wallet-prefund dogfood still depended on a funded exportable buyer wallet
- Railway production still had no `RHUMB_DOGFOOD_WALLET_PRIVATE_KEY`
- weakest callable runtime-backed depth was **4** across **6** providers
- `apollo` was the next freshness-ordered provider in that depth-4 bucket after the Algolia rerun

So this pass stayed on the callable-review freshness lane instead of reopening the still-blocked dogfood lane.

## What shipped

### 1) Fresh Apollo runtime rerun via the temp review-agent rail
Used the linked Railway production context to:
- seed a temp org wallet
- create a temp review agent
- grant only Apollo access
- run `data.enrich_person` through Rhumb-managed execution
- compare against direct Apollo control on the same live email input

Runtime artifact:
- `artifacts/runtime-review-pass-20260330T225059Z-apollo-current-depth5.json`

Live parity input:
- `{"email":"tim@apple.com"}`

Observed parity:
- `name` matched exactly: `Yenni Tim`
- `title` matched exactly: `Founder and Director, UNSW PRAxIS (Practice x Implementation Science) Lab`
- `organization_name` matched exactly: `UNSW Business School`
- `linkedin_url` matched exactly: `http://www.linkedin.com/in/yennitim`
- `email_status` matched exactly: `null`

Execution ids / temp rail:
- temp org: `org_runtime_review_apollo_20260330t225059z`
- temp agent: `f83fb93c-aded-4c90-8c2c-d28a3e183cf5`
- Rhumb execution: `exec_f5da51d430684f74aac91b5d535b0bb6`

### 2) Reusable operator helper
Added a repeatable helper for this rerun pattern:
- `scripts/runtime_review_apollo_depth5_20260330.py`

The script:
- bootstraps temp billing
- provisions a scoped review agent
- runs Rhumb-managed Apollo execution
- runs direct Apollo control with the same email input
- checks parity on `name`, `title`, `organization_name`, `linkedin_url`, and `email_status`
- publishes the runtime-backed evidence/review pair
- disables the temp review agent in `finally`

### 3) Public trust-surface publication
Published the new runtime-backed evidence/review pair to production.

Publication artifact:
- `artifacts/runtime-review-publication-2026-03-30-apollo-depth5.json`

Inserted rows:
- evidence: `e49fd4e0-6a49-44a2-a2e8-697783bef4ad`
- review: `77a22234-986f-48f9-b3fc-dca1e4444b82`

## Validation

### Counts before publication
From the runtime artifact:
- published reviews: **9**
- runtime-backed reviews: **4**

### Public audit after publication
Artifact:
- `artifacts/callable-review-coverage-2026-03-30-post-apollo-depth5.json`

Result:
- weakest runtime-backed callable depth: **4**
- weakest-bucket provider count: **5**
- `apollo` runtime-backed reviews: **5**
- total public reviews: **10**
- freshest evidence: `2026-03-30T22:51:06Z`

### New weakest-bucket state
After the Apollo rerun, the depth-4 freshness bucket is now:
- `apify`
- `e2b`
- `exa`
- `replicate`
- `unstructured`

By freshness ordering, the next honest callable-review target is now **Exa**.

## Outcome
This pass kept the build loop on the next honest unblocked lane:
- dogfood remained blocked on funded buyer-wallet availability
- Google AI wiring stayed closed as already-live work
- the next freshness-ordered depth-4 callable provider was rerun and published

Apollo moved **4 → 5** runtime-backed reviews, and the current weakest-bucket size shrank from **6 → 5**.

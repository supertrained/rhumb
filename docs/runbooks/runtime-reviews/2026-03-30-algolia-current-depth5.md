# 2026-03-30 — Algolia current-depth freshness rerun (depth 4 → 5)

## Goal
Advance the next honest unblocked callable-review lane after the callable floor reached depth 4 across all providers.

At the start of this pass:
- wallet-prefund dogfood still depended on a funded exportable buyer wallet
- Railway production still had no `RHUMB_DOGFOOD_WALLET_PRIVATE_KEY`
- weakest callable runtime-backed depth was **4** across **7** providers
- `algolia` was the **stalest** provider in that depth-4 bucket by freshest public evidence timestamp

So this pass stayed on the callable-review freshness lane instead of reopening the still-blocked dogfood lane.

## What shipped

### 1) Fresh Algolia runtime rerun via the temp review-agent rail
Used the linked Railway production context to:
- seed a temp org wallet
- create a temp admin agent
- grant only Algolia access
- run `search.autocomplete` through Rhumb-managed execution
- compare against direct Algolia control on the same live index + query

Runtime artifact:
- `artifacts/runtime-review-pass-20260330T204402Z-algolia-current-depth5.json`

Live parity inputs:
- index: `rhumb_test`
- query: `rhumb`

Observed parity:
- `nbHits` matched exactly: **1 / 1**
- top `objectID` matched exactly: `1`
- top `name` matched exactly: `Rhumb Runtime Test`

Execution ids / temp rail:
- temp org: `org_runtime_review_algolia_20260330t204402z`
- temp agent: `5c5d36e1-75f1-4244-9599-e5f5f1a395a2`
- Rhumb execution: `exec_e967ac6d13a14fb88ca375970a21c69e`

### 2) Reusable operator helper
Added a repeatable helper for this rerun pattern:
- `scripts/runtime_review_algolia_depth5_20260330.py`

The script:
- bootstraps temp billing
- provisions a scoped review agent
- runs Rhumb-managed Algolia execution
- runs direct Algolia control with the same index + query
- checks `nbHits` / top `objectID` / top `name` parity
- publishes the runtime-backed evidence/review pair

### 3) Public trust-surface publication
Published the new runtime-backed evidence/review pair to production.

Publication artifact:
- `artifacts/runtime-review-publication-2026-03-30-algolia-depth5.json`

Inserted rows:
- evidence: `83082af3-7f44-4f28-9c6c-f69f47bc56ae`
- review: `23ba6621-8762-4488-bc4f-28db14be720a`

## Validation

### Counts before publication
From the runtime artifact:
- published reviews: **9**
- runtime-backed reviews: **4**

### Public audit after publication
Artifact:
- `artifacts/callable-review-coverage-2026-03-30-post-algolia-depth5.json`

Result:
- weakest runtime-backed callable depth: **4**
- weakest-bucket provider count: **6**
- `algolia` runtime-backed reviews: **5**
- total public reviews: **10**
- freshest evidence: `2026-03-30T20:44:08Z`

### New weakest-bucket state
After the Algolia rerun, the depth-4 freshness bucket is now:
- `apify`
- `apollo`
- `e2b`
- `exa`
- `replicate`
- `unstructured`

By freshness ordering, the next honest callable-review target is now **Apollo**.

## Outcome
This pass kept the build loop on the next honest unblocked lane:
- dogfood remained blocked on funded buyer-wallet availability
- Google AI wiring stayed closed as already-live work
- the stalest remaining depth-4 callable provider was rerun and published

Algolia moved **4 → 5** runtime-backed reviews, and the current weakest-bucket size shrank from **7 → 6**.

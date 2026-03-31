# Current-depth runtime review — Apify depth 5 publication

Date: 2026-03-30
Owner: Pedro / Keel runtime review loop
Priority: next freshness-ordered provider in the weakest callable-review bucket after the Unstructured pass

## Blocker re-check before the pass

Before touching the next lane, I re-checked the top blocker truth:
- `RHUMB_DOGFOOD_WALLET_PRIVATE_KEY` is still absent in Railway production
- wallet-prefund dogfood therefore remains blocked by funded exportable buyer-wallet availability, not by missing product code
- Google AI wiring is already live and repeatedly verified, so it is not the active lane

That left the honest unblocked move: continue callable-review freshness reruns inside the remaining depth-4 bucket.

## Why Apify was next

Fresh cache-busted public callable audit before the pass:
- callable providers: **16**
- weakest runtime-backed callable depth: **4**
- weakest bucket: `apify`, `e2b`, `replicate`
- artifact: `artifacts/callable-review-coverage-2026-03-30-pre-apify-depth5.json`

Within that bucket, **Apify** was the stalest provider by freshest public runtime evidence timestamp, so it became the next honest target.

## Runtime-review rail used

- temp org: `org_runtime_review_apify_20260331t024603z_ca4c2cd0`
- seeded balance: `5000` cents
- temp review agent: `d743bce3-de16-4b15-9c05-c57c9d47e9ed`
- service grant: `apify` only
- temp access row: `84c9692a-11fb-4e70-9d37-7c14ef52e7f4`
- execution rail: normal `X-Rhumb-Key` path via Railway production context
- cleanup: temp review agent disabled after publish

## Managed execution

- Capability: `scrape.extract`
- Provider: `apify`
- Credential mode: `rhumb_managed`
- Estimate: **200 OK**
- Execute wrapper: **200 OK**
- Upstream status: **201**
- Execution id: `exec_e76ed25524d84304898f0363953101e3`
- Rhumb run id: `cws1hpNVs17yGA0Uo`
- Rhumb dataset id: `cMYPhqcvnxGER0eRq`
- Target: `https://example.com`

Rhumb-managed output sample matched on:
- `url`: `https://example.com/`
- `metadata.title`: `Example Domain`
- `markdown`: exact match

## Direct provider control

- Endpoint: `POST https://api.apify.com/v2/acts/apify~website-content-crawler/runs?waitForFinish=60`
- Dataset fetch: `GET https://api.apify.com/v2/datasets/{datasetId}/items?clean=true&limit=1`
- Auth: Railway production `RHUMB_CREDENTIAL_APIFY_API_TOKEN`
- Same payload and same one-page target as the Rhumb-managed path
- Direct status: **201 Created**
- Direct run id: `uy3n830pou6dMjfGP`
- Direct dataset id: `pPgIRPcG1LLdOMWaq`

Direct control produced the same sample values:
- `url`: `https://example.com/`
- `metadata.title`: `Example Domain`
- `markdown`: exact match

## Parity verdict

Managed and direct executions matched exactly on:
- `url`
- `metadata.title`
- `markdown`

Verdict: **production parity passed cleanly**.

## Public trust surface update

Published fresh runtime-backed rows:
- evidence: `b234e69e-672b-43c6-9fa9-1c2c40db6d9b`
- review: `9f34d660-1148-4135-aca0-73537c52524e`

Artifacts:
- `artifacts/runtime-review-pass-20260331T024603Z-apify-current-depth5.json`
- `artifacts/runtime-review-publication-2026-03-30-apify-depth5.json`
- `artifacts/callable-review-coverage-2026-03-30-pre-apify-depth5.json`
- `artifacts/callable-review-coverage-2026-03-30-post-apify-depth5.json`
- `scripts/runtime_review_apify_depth5_20260330.py`

## Coverage impact

Post-publish audit confirmed:
- Apify runtime-backed review depth: **4 → 5**
- total published Apify reviews: **9 → 10**
- weakest callable-review bucket size: **3 → 2**
- weakest runtime-backed callable depth stays **4**, now across:
  - `e2b`
  - `replicate`

By freshness ordering, the next honest target is now **`e2b`**.

## Verdict

- wallet-prefund dogfood is still honestly blocked by funded-wallet availability
- Google AI wiring remains done and out of the critical path
- Apify is freshly re-verified in production at depth 5
- no new Rhumb execution-layer repair was required in this run because managed/direct parity held cleanly

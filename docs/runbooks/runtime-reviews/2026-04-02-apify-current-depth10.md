# Runtime review loop — Apify depth 10

Date: 2026-04-02
Owner: Pedro / Keel runtime review loop

## Why Apify was selected

Fresh callable coverage before the pass showed:
- callable providers: **16**
- weakest claim-safe runtime depth: **9**
- weakest bucket: `github`, `slack`, `stripe`, `apify`, `replicate`, `algolia`, `twilio`

Within that weakest bucket, **Apify** was the stalest provider by freshest public runtime evidence timestamp (`2026-03-31T02:46:49Z`), so it was the honest next freshness target.

Pre-pass artifact:
- `artifacts/callable-review-coverage-2026-04-02-pre-apify-current-pass-from-cron-1937.json`

## Rhumb execution

- Capability: `scrape.extract`
- Provider: `apify`
- Credential mode: `rhumb_managed`
- Estimate: **200**
- Execute: **200**
- Upstream provider status through Rhumb: **201**
- Provider used: **`apify`**
- Execution id: `exec_55a6f832da2540d6905a4119400c2bd4`
- Rhumb run id: `kldSwXmevtmGDNKEb`
- Rhumb dataset id: `Rtrc2HbbcXM2zCXO9`
- Input:
  - target: `https://example.com`
  - crawl: one page, depth `0`, max pages `1`

Rhumb returned the expected sample page:
- `url`: `https://example.com/`
- `metadata.title`: `Example Domain`
- `markdown`: exact example.com body markdown

## Direct provider control

- Endpoint: `POST https://api.apify.com/v2/acts/apify~website-content-crawler/runs?waitForFinish=60`
- Dataset fetch: `GET https://api.apify.com/v2/datasets/{datasetId}/items?clean=true&limit=1`
- Status: **201**
- Auth: live Railway production `RHUMB_CREDENTIAL_APIFY_API_TOKEN`
- Input: same one-page crawler payload against the same target
- Direct run id: `WgNsMVKBZqc0i7moy`
- Direct dataset id: `IawqfMUuZdFtR4tIz`

Direct control returned the same sample values:
- `url`: `https://example.com/`
- `metadata.title`: `Example Domain`
- `markdown`: exact match

## Parity verdict

Managed and direct executions matched exactly on:
- `url`
- `metadata.title`
- `markdown`

Verdict: **PASS.** No execution-layer investigation or repair was required.

## Published trust rows

- evidence: `43d72678-719c-46ba-b08a-6f6e0a7db6fb`
- review: `608e85a7-d77b-4a77-9f25-603579e13e35`

## Coverage impact

Post-publish audit confirmed:
- Apify claim-safe runtime-backed reviews: **9 → 10**
- total published Apify reviews: **10 → 11**
- weakest callable depth stays **9**
- Apify leaves the weakest bucket

Post-pass weakest bucket:
- `github`
- `slack`
- `stripe`
- `replicate`
- `algolia`
- `twilio`

Post-pass artifact:
- `artifacts/callable-review-coverage-2026-04-02-post-apify-current-pass-from-cron-1943.json`

## Artifacts

- `artifacts/runtime-review-pass-20260403T024000Z-apify-depth10.json`
- `artifacts/runtime-review-publication-2026-04-02-apify-depth10.json`
- `artifacts/callable-review-coverage-2026-04-02-pre-apify-current-pass-from-cron-1937.json`
- `artifacts/callable-review-coverage-2026-04-02-post-apify-current-pass-from-cron-1943.json`
- `scripts/runtime_review_apify_depth10_20260402.py`

## Honest next runtime-review target

With Apify lifted to depth 10, the freshness-ordered next weakest callable target is now **Replicate**.

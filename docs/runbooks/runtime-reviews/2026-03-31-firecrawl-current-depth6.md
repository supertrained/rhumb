# 2026-03-31 — Firecrawl current-depth6 publication

## Goal
Advance the next honest unblocked callable-review freshness lane after the dogfood rerun stalled locally on a missing exported `RHUMB_DOGFOOD_API_KEY` in this shell.

At the start of this pass:
- the public callable audit showed weakest claim-safe runtime-backed depth **5** across **8** providers
- `firecrawl` was the stalest provider in that weakest bucket
- the next honest move was not more product theory — it was a fresh production parity pass and publication

## What shipped

### 1) Fresh Firecrawl runtime pass via the production env rail
Used the linked Railway production context to:
- seed a temp org wallet with `5000` cents
- create a temp admin review agent
- grant only Firecrawl access
- run `scrape.extract` through Rhumb-managed execution
- compare against direct Firecrawl control on the same stable public target
- disable the temp review agent after the pass

Runtime artifact:
- `artifacts/runtime-review-pass-20260331T201229Z-firecrawl-current-depth6.json`

Live target used:
- URL: `https://example.com`
- formats: `markdown`

Observed parity:
- Rhumb-managed upstream status: **200**
- direct Firecrawl status: **200**
- `success=true` matched on both sides
- page title matched exactly: **`Example Domain`**
- markdown presence matched on both sides

Execution / temp rail:
- temp org: `org_runtime_review_firecrawl_20260331t201229z`
- Rhumb execution: `exec_bda3c08b916241c2966bb196ff3bd31a`

### 2) Public trust-surface publication
Published the new runtime-backed evidence/review pair to production.

Publication artifact:
- `artifacts/runtime-review-publication-2026-03-31-firecrawl-depth6.json`

Inserted rows:
- evidence: `34ad7a76-dbed-43cc-97fa-112348ee7679`
- review: `77eea460-776c-4f57-b0db-24a13b9e4e7e`

### 3) Public verification artifacts
- pre-audit: `artifacts/callable-review-coverage-2026-03-31-pre-firecrawl-depth6-from-cron.json`
- post-audit: `artifacts/callable-review-coverage-2026-03-31-post-firecrawl-depth6-from-cron.json`

## Validation

### Public audit before publication
Artifact:
- `artifacts/callable-review-coverage-2026-03-31-pre-firecrawl-depth6-from-cron.json`

Result:
- weakest claim-safe callable depth: **5**
- weakest-bucket provider count: **8**
- `firecrawl` sat in that bucket at depth **5**

### Public audit after publication
Artifact:
- `artifacts/callable-review-coverage-2026-03-31-post-firecrawl-depth6-from-cron.json`

Result:
- `firecrawl` moved **5 → 6** claim-safe runtime-backed reviews
- weakest callable depth stayed **5**
- weakest-bucket provider count shrank **8 → 7**

Remaining weakest-bucket providers after publish:
- `algolia`
- `apify`
- `apollo`
- `e2b`
- `exa`
- `replicate`
- `unstructured`

## Outcome
This pass kept the callable freshness rotation moving with fresh production evidence instead of letting the lane stall on a local dogfood-key export gap.

Firecrawl moved from claim-safe depth **5 → 6**, and the weakest callable bucket shrank from **8 → 7** providers.

## Next move
- recover/export the dedicated dogfood API key and rerun the full Layer 1 + Layer 2 v2 dogfood harness from this shell
- otherwise keep grinding the weakest callable freshness bucket, with **`algolia`** now the next honest target

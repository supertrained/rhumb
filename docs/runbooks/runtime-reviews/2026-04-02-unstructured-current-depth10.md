# Runtime review loop — Unstructured depth 10

Date: 2026-04-02
Owner: Pedro / Keel runtime review loop

## Why Unstructured was selected

Fresh callable coverage before the pass showed:
- callable providers: **16**
- weakest claim-safe runtime depth: **9**
- weakest bucket: `github`, `slack`, `stripe`, `apify`, `replicate`, `unstructured`, `algolia`, `twilio`

Within that weakest bucket, **Unstructured** was the stalest provider by freshest public runtime evidence timestamp (`2026-03-31T00:46:09Z`), so it was the honest next freshness target.

Pre-pass artifact:
- `artifacts/callable-review-coverage-2026-04-02-pre-unstructured-current-pass-from-cron-1734.json`

## Rhumb execution

- Capability: `document.parse`
- Provider: `unstructured`
- Credential mode: `rhumb_managed`
- Estimate: **200**
- Execute: **200**
- Upstream provider status through Rhumb: **200**
- Provider used: **`unstructured`**
- Execution id: `exec_255d5a7273bb4fb6bfaeed3108b06c6b`
- Input:
  - strategy: `fast`
  - file: `runtime-review-unstructured-depth10.txt`

Rhumb returned two parsed elements:
1. `Title` → `Rhumb Runtime Review`
2. `NarrativeText` → `Unstructured should parse this short sample into a Title and a NarrativeText block.`

## Direct provider control

- Endpoint: `POST https://api.unstructuredapp.io/general/v0/general`
- Status: **200**
- Auth: `Unstructured API Key` from 1Password
- Input: same file + same `strategy=fast`

Direct control returned the same two elements in the same order:
1. `Title`
2. `NarrativeText`

## Parity verdict

Managed and direct executions matched exactly on:
- element count (**2 = 2**)
- element type ordering (`Title`, `NarrativeText`)
- extracted text content

Verdict: **PASS.** No execution-layer investigation or repair was required.

## Published trust rows

- evidence: `1c4be8e0-07a8-4aac-8120-1c7abb1576c1`
- review: `2fdf6008-456d-462e-bc7b-051940a1b39f`

## Coverage impact

Post-publish audit confirmed:
- Unstructured claim-safe runtime-backed reviews: **9 → 10**
- total published Unstructured reviews: **10 → 11**
- weakest callable depth stays **9**
- Unstructured leaves the weakest bucket

Post-pass weakest bucket:
- `github`
- `slack`
- `stripe`
- `apify`
- `replicate`
- `algolia`
- `twilio`

Post-pass artifact:
- `artifacts/callable-review-coverage-2026-04-02-post-unstructured-current-pass-from-cron-1740.json`

## Artifacts

- `artifacts/runtime-review-pass-20260403T004026Z-unstructured-depth10.json`
- `artifacts/runtime-review-publication-2026-04-02-unstructured-depth10.json`
- `artifacts/callable-review-coverage-2026-04-02-pre-unstructured-current-pass-from-cron-1734.json`
- `artifacts/callable-review-coverage-2026-04-02-post-unstructured-current-pass-from-cron-1740.json`
- `scripts/runtime_review_unstructured_depth10_20260402.py`

## Honest next runtime-review target

With Unstructured lifted to depth 10, the freshness-ordered next weakest callable target is now **Apify**.

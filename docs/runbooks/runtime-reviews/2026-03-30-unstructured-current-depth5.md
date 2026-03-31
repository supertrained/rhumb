# Current-depth runtime review — Unstructured depth 5 publication

Date: 2026-03-30
Owner: Pedro / Keel runtime review loop
Priority: next freshness-ordered provider in the weakest callable-review bucket after the Exa pass

## Blocker re-check before the pass

Before touching the next lane, I re-checked the stated top blocker:
- `RHUMB_DOGFOOD_WALLET_PRIVATE_KEY` is still absent
- wallet-prefund dogfood therefore remains blocked by funded exportable buyer-wallet availability, not by missing product code
- Google AI wiring is already live and verified, so it is not the active lane

That left the honest unblocked move: continue callable-review freshness reruns inside the remaining depth-4 bucket.

## Why Unstructured was next

Fresh cache-busted public callable audit before the pass:
- callable providers: **16**
- weakest runtime-backed callable depth: **4**
- weakest bucket: `apify`, `e2b`, `replicate`, `unstructured`
- artifact: `artifacts/callable-review-coverage-2026-03-30-pre-unstructured-depth5.json`

Among that remaining bucket, **Unstructured** was the stalest provider by freshest public runtime evidence timestamp, so it became the next honest target.

## Runtime-review rail used

- temp org: `org_runtime_review_unstructured_20260331t004603z`
- seeded balance: `5000` cents
- temp review agent: `86d969a7-0355-42b7-b269-2d6393845c9b`
- service grant: `unstructured` only
- temp access row: `dcdc154f-bf2b-49a1-9f18-845a0ffcb626`
- execution rail: normal `X-Rhumb-Key` path via Railway production context
- cleanup: temp review agent disabled after publish

## Managed execution

- Capability: `document.parse`
- Provider: `unstructured`
- Credential mode: `rhumb_managed`
- Estimate: **200 OK**
- Execute: **200 OK**
- Upstream status: **200**
- Execution id: `exec_7a9eaa96290343b5a360869f86a05946`
- Input:
  - strategy: `fast`
  - file: `runtime-review-unstructured-depth5.txt`

Rhumb returned two parsed elements:
1. `Title` → `Rhumb Runtime Review`
2. `NarrativeText` → `Unstructured should parse this short sample into a Title and a NarrativeText block.`

## Direct provider control

- Endpoint: `POST https://api.unstructuredapp.io/general/v0/general`
- Auth: Railway production `RHUMB_CREDENTIAL_UNSTRUCTURED_API_KEY`
- Input: same file + same `strategy=fast`
- Direct result: **200 OK**

Direct control returned the same two elements in the same order:
1. `Title`
2. `NarrativeText`

## Parity verdict

Managed and direct executions matched exactly on:
- element count (**2 = 2**)
- element type ordering (`Title`, `NarrativeText`)
- parsed text content

Verdict: **production parity passed cleanly**.

## Public trust surface update

Published fresh runtime-backed rows:
- evidence: `2a0157f9-9990-406d-9643-72ab77adf576`
- review: `edf9a6a7-dcc8-40b9-af1a-2582e8b0f635`

Artifacts:
- `artifacts/runtime-review-pass-20260331T004603Z-unstructured-current-depth5.json`
- `artifacts/runtime-review-publication-2026-03-30-unstructured-depth5.json`
- `artifacts/callable-review-coverage-2026-03-30-pre-unstructured-depth5.json`
- `artifacts/callable-review-coverage-2026-03-30-post-unstructured-depth5.json`
- `scripts/runtime_review_unstructured_depth5_20260330.py`

## Coverage impact

Post-publish audit confirmed:
- Unstructured runtime-backed review depth: **4 → 5**
- total published Unstructured reviews: **9 → 10**
- weakest callable-review bucket size: **4 → 3**
- weakest runtime-backed callable depth stays **4**, now across:
  - `apify`
  - `e2b`
  - `replicate`

By freshness ordering, the next honest target is now **`apify`**.

## Verdict

- wallet-prefund dogfood is still honestly blocked by funded-wallet availability
- Google AI wiring remains done and out of the critical path
- Unstructured is freshly re-verified in production at depth 5
- no new Rhumb execution-layer repair was required in this run because no managed/direct divergence appeared

# Current-pass runtime review — Unstructured rerun

Date: 2026-03-28
Owner: Pedro / Keel runtime review loop
Priority: Next weakest-bucket callable provider

## Why Unstructured

Telemetry MVP is done, Google AI is already live + rerun-verified, and the buyer-side x402 dogfood proof is still blocked on recovering the funded Awal wallet identity.

That left the next cleanest unblocked lane as another callable-provider depth pass.

Unstructured was the right target because:
- it was still sitting in the weakest callable-review bucket at **1 runtime-backed review**
- the direct control path is simple and low-risk (`POST /general/v0/general` with a file upload)
- the Rhumb execution lane is already proven on `document.parse`, so this pass could focus on fresh parity and trust-surface depth rather than bug hunting

## Test setup

### Rhumb Resolve execution
- Endpoint: `POST /v1/capabilities/document.parse/execute`
- Provider: `unstructured`
- Credential mode: `rhumb_managed`
- Interface tag: `runtime_review`
- Input file: `runtime-review-unstructured.txt`
- File contents: short plain-text sample with one title line and one narrative paragraph
- Parse strategy: `fast`

### Direct provider control
- Endpoint: `POST https://api.unstructuredapp.io/general/v0/general`
- Auth: live `RHUMB_CREDENTIAL_UNSTRUCTURED_API_KEY` from Railway env
- Input: same text file, same `strategy=fast`

### Runtime-review rail used
- Seeded a temporary internal org wallet with `5000` cents for execution headroom
- Created a temporary review agent via the live admin-agent route
- Granted only `unstructured`
- Executed through the normal `X-Rhumb-Key` rail
- Published evidence + review directly to the public trust tables after parity passed

## Results

### Rhumb Resolve
- Estimate: **200**
- Capability: `document.parse`
- Endpoint pattern: `POST /general/v0/general`
- Execution result: **succeeded**
- Execution id: `exec_642fa43cb10440818ab9cec0930e0472`
- Upstream status: **200**
- Output shape:
  - `Title`
  - `NarrativeText`
- Element count: **2**

### Direct Unstructured control
- Result: **succeeded**
- HTTP status: **200**
- Output shape:
  - `Title`
  - `NarrativeText`
- Element count: **2**

## Comparison

| Dimension | Rhumb Resolve | Direct Unstructured |
| --- | --- | --- |
| Reachability | Healthy | Healthy |
| Auth path | Rhumb-managed credential injection | Direct provider key from Railway env |
| Output parity | Exact element-type match | Baseline |
| Element count | 2 | 2 |
| Verdict | Working production integration | Provider API healthy |

## Public trust surface update

Published fresh runtime-backed artifacts:
- Evidence: `e04584b2-52a8-4d6d-bc0d-baf501dd067d`
- Review: `781fdf10-58c3-4bd0-978d-ee21d28129c6`

Public depth moved:
- Unstructured runtime-backed reviews: **1 → 2**
- Total published reviews: **6 → 7**

Fresh artifact bundle:
- `rhumb/artifacts/runtime-review-pass-20260328T072502Z-unstructured.json`
- `rhumb/artifacts/callable-review-coverage-2026-03-28-post-unstructured.json`

## Coverage impact

After the rerun, the callable weakest bucket dropped from **5 providers to 4**.

Remaining weakest-bucket callable providers:
- `algolia`
- `apify`
- `e2b`
- `replicate`

## Verdict

**Unstructured is re-verified in production on the current pass.**

No new product bug surfaced. Rhumb Resolve and direct provider control matched exactly on the deterministic output shape for the same file, and the public trust surface now reflects the extra live-backed proof.

## Next move

Stay on the same rail and take the next cleanest provider from the remaining weakest bucket, with `replicate` or `apify` as the best immediate candidates if x402 dogfood is still blocked.
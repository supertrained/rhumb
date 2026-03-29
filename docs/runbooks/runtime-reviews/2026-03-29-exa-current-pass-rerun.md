# Current-pass runtime review — Exa rerun

Date: 2026-03-29
Owner: Pedro / Keel runtime review loop
Priority: Next weakest-bucket callable provider after Apollo

## Why Exa

This pass first checked the honest top priority: whether a funded operator-controlled Base EOA with an exportable private key was actually available for `scripts/wallet_prefund_dogfood.py`.

No such key surfaced in the live operator env for this pass, so the x402 buyer-proof lane remained blocked by wallet availability rather than missing product code.

That meant the cleanest unblocked move was to keep shrinking the weakest callable-review bucket.

Exa was a good next target because:
- it was still sitting in the weakest callable-review bucket at **2 runtime-backed reviews**
- the direct control path is simple and deterministic (`POST https://api.exa.ai/search`)
- Rhumb already has a healthy `search.query` execution lane for Exa, so this pass could focus on fresh production parity and trust-surface depth

## Test setup

### Rhumb Resolve execution
- Endpoint: `POST /v1/capabilities/search.query/execute`
- Provider: `exa`
- Credential mode: `rhumb_managed`
- Interface tag: `runtime_review`
- Query: `best AI agent observability tools`
- `numResults`: `3`

### Direct provider control
- Endpoint: `POST https://api.exa.ai/search`
- Auth: live `RHUMB_CREDENTIAL_EXA_API_KEY` from Railway env
- Query: same query, same `numResults=3`
- Client note: sent with a normal browser-style `User-Agent`

### Runtime-review rail used
- Seeded a temporary internal org wallet with `5000` cents for execution headroom
- Created a temporary review agent via the live admin-agent route
- Granted only `exa`
- Executed through the normal `X-Rhumb-Key` rail
- Published evidence + review directly to the public trust tables after parity passed
- Disabled the temporary review agents after publish

## Results

### Rhumb Resolve
- Estimate: **200 OK**
- Capability: `search.query`
- Estimated cost: **$0.001**
- Endpoint pattern: `POST /search`
- Execution result: **succeeded**
- Execution id: `exec_652b47dbe17d4cafb4f9199869879858`
- Upstream status: **200**
- Result count: **3**
- Top result:
  - Title: `5 best AI agent observability tools for agent reliability in 2026 - Articles`
  - URL: `https://www.braintrust.dev/articles/best-ai-agent-observability-tools-2026`

### Direct Exa control
- Result: **succeeded**
- HTTP status: **200**
- Result count: **3**
- Top result:
  - Title: `5 best AI agent observability tools for agent reliability in 2026 - Articles`
  - URL: `https://www.braintrust.dev/articles/best-ai-agent-observability-tools-2026`

## Comparison

| Dimension | Rhumb Resolve | Direct Exa |
| --- | --- | --- |
| Reachability | Healthy | Healthy |
| Auth path | Rhumb-managed credential injection | Direct provider key from Railway env |
| Result count | 3 | 3 |
| Top title parity | Exact match | Baseline |
| Top URL parity | Exact match | Baseline |
| Verdict | Working production integration | Provider API healthy |

## Public trust surface update

Published fresh runtime-backed artifacts:
- Evidence: `af96f19a-da05-43c7-a8e0-dfd064fbad36`
- Review: `f98e665d-42d4-4e02-87b4-dd4de3c45f38`

Public depth moved:
- Exa runtime-backed reviews: **2 → 3**
- Total published reviews: **7 → 8**

Fresh artifact bundle:
- `rhumb/artifacts/runtime-review-pass-20260329T182105Z-exa-current-pass.json`
- `rhumb/artifacts/callable-review-coverage-2026-03-29-post-exa.json`

## Coverage impact

After the rerun, the callable weakest bucket dropped from **5 providers to 4**.

Remaining weakest-bucket callable providers:
- `apify`
- `e2b`
- `replicate`
- `unstructured`

Current weakest runtime-backed callable depth: **2**.

## Verdict

**Exa is re-verified in production on the current pass.**

Rhumb Resolve and direct Exa control matched exactly on result count, top title, and top URL for the same search query, and the public trust surface now reflects the extra live-backed proof.

## Next move

Stay honest about the dogfood blocker:
- if a funded exportable Base EOA appears, immediately run `scripts/wallet_prefund_dogfood.py`
- if not, keep grinding the remaining weakest callable-review bucket, with `apify`, `e2b`, `replicate`, and `unstructured` as the current candidates

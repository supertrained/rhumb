# Current-pass runtime review — Tavily depth-4 publication

Date: 2026-03-29
Owner: Pedro / Keel runtime review loop
Priority: Next weakest-bucket callable provider after Google AI

## Why Tavily

This pass kept the same honest ordering:

1. telemetry is already done
2. wallet-prefund dogfood is still the top product-proof lane when a funded exportable Base EOA is actually available
3. if that wallet rail is still blocked by operator-controlled funding/key access, keep shrinking the weakest callable-review bucket instead of pretending the blocker moved

No funded exportable buyer EOA surfaced during this pass, so the dogfood lane remained externally blocked.

That made the cleanest unblocked move another weakest-bucket callable depth lift.

Tavily was the best next target because:
- it was still sitting in the weakest callable-review bucket at **3 runtime-backed reviews**
- it had the oldest freshest-evidence timestamp in the bucket
- the direct control path is simple and deterministic (`POST https://api.tavily.com/search`)
- Rhumb already had a healthy `search.query` lane for Tavily, so this pass could focus on fresh production parity and trust-surface depth

## Test setup

### Rhumb Resolve execution
- Endpoint: `POST /v1/capabilities/search.query/execute`
- Provider: `tavily`
- Credential mode: `rhumb_managed`
- Interface tag: `runtime_review`
- Query: `best AI agent observability tools`
- `search_depth`: `basic`
- `max_results`: `5`

### Direct provider control
- Endpoint: `POST https://api.tavily.com/search`
- Auth: live `RHUMB_CREDENTIAL_TAVILY_API_KEY` from Railway env
- Query: same query, same `search_depth=basic`, same `max_results=5`

### Runtime-review rail used
- Seeded a temporary internal org wallet with `5000` cents for execution headroom
- Created a temporary review agent directly through the live identity store on Railway-backed production env
- Granted only `tavily`
- Executed through the normal `X-Rhumb-Key` rail
- Published evidence + review directly to the public trust tables after parity passed
- Disabled the temporary review agent after publish

## Results

### Rhumb Resolve
- Estimate: **200 OK**
- Capability: `search.query`
- Estimated cost: **$0.001**
- Endpoint pattern: `POST /search`
- Execution result: **succeeded**
- Execution id: `exec_f57bfd5523604230b6bf4e1ae6b453e1`
- Upstream status: **200**
- Result count: **5**
- Top result:
  - Title: `Best Observability Tools with AI-Powered Insights (2026) - Metoro`
  - URL: `https://metoro.io/blog/best-observability-tools-with-ai`

### Direct Tavily control
- Result: **succeeded**
- HTTP status: **200**
- Result count: **5**
- Top result:
  - Title: `Best Observability Tools with AI-Powered Insights (2026) - Metoro`
  - URL: `https://metoro.io/blog/best-observability-tools-with-ai`

## Comparison

| Dimension | Rhumb Resolve | Direct Tavily |
| --- | --- | --- |
| Reachability | Healthy | Healthy |
| Auth path | Rhumb-managed credential injection | Direct provider key from Railway env |
| Result count | 5 | 5 |
| Top title parity | Exact match | Baseline |
| Top URL parity | Exact match | Baseline |
| Verdict | Working production integration | Provider API healthy |

## Public trust surface update

Published fresh runtime-backed artifacts:
- Evidence: `6c296771-5ca3-4f62-a620-573756eb2d94`
- Review: `035689ec-f458-417d-95d6-5f4688826215`

Published source refs:
- `runtime-review:tavily:20260330T042750Z`

Public depth moved:
- Tavily runtime-backed reviews: **3 → 4**
- Total published reviews: **8 → 9**

Fresh artifact bundle:
- `rhumb/artifacts/runtime-review-pass-20260330T042750Z-tavily-current.json`
- `rhumb/artifacts/callable-review-coverage-2026-03-30-pre-cron-loop.json`
- `rhumb/artifacts/callable-review-coverage-2026-03-30-post-tavily.json`

## Coverage impact

After the rerun, the callable weakest bucket dropped from **9 providers to 8**.

Remaining weakest-bucket callable providers:
- `algolia`
- `apify`
- `apollo`
- `e2b`
- `exa`
- `firecrawl`
- `replicate`
- `unstructured`

Current weakest runtime-backed callable depth: **3**.

Providers now above that bucket:
- `brave-search-api` at depth **4**
- `google-ai` at depth **4**
- `tavily` at depth **4**

## Verdict

**Tavily is re-verified in production on the current pass.**

Rhumb Resolve and direct Tavily control matched exactly on result count, top title, and top URL for the same search query, and the public trust surface now reflects the extra live-backed proof.

## Next move

Stay honest about the dogfood blocker:
- if a funded exportable Base EOA appears, immediately run `scripts/wallet_prefund_dogfood.py`
- if not, keep grinding the remaining weakest callable-review bucket, with `firecrawl`, `algolia`, `apollo`, `apify`, `exa`, `e2b`, `replicate`, and `unstructured` as the current candidates

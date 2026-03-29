# Phase 3 runtime review — Tavily current-pass rerun II

Date: 2026-03-28
Owner: Pedro / Keel runtime review loop
Priority: Mission 1 weakest-bucket runtime verification after Mission 0 PDL reconfirm
Status: PASS — fresh runtime-backed evidence and review published

## Why Tavily

I queried the live callable inventory and refreshed public runtime-backed review coverage before choosing the next provider.

Current public callable state at pass start:
- callable providers: **16**
- weakest runtime-backed depth: **2**
- tied weakest bucket:
  - `algolia`
  - `apify`
  - `apollo`
  - `e2b`
  - `exa`
  - `firecrawl`
  - `google-ai`
  - `replicate`
  - `tavily`
  - `unstructured`

After skipping PDL because Mission 0 had already re-verified it in this pass, **Tavily** was the cleanest weakest-bucket lane because:
- it is callable in production
- it is read-only and low-side-effect
- direct provider control is simple and available in 1Password
- it supports a clean same-input parity check on stable result fields

## Test setup

### Rhumb Resolve execution
- Endpoint: `POST /v1/capabilities/search.query/execute`
- Estimate: `GET /v1/capabilities/search.query/execute/estimate?provider=tavily&credential_mode=rhumb_managed`
- Capability: `search.query`
- Provider: `tavily`
- Credential mode: `rhumb_managed`
- Interface: `runtime_review`
- Input:
  ```json
  {
    "query": "best AI agent observability tools",
    "search_depth": "basic",
    "max_results": 5
  }
  ```

### Direct provider control
- Endpoint: `POST https://api.tavily.com/search`
- Auth: direct Tavily API key
- Input: same query, search depth, and result count

## Results

### Rhumb Resolve
- Estimate: `200 OK`
- Cost estimate: `$0.001`
- Circuit state: `closed`
- Endpoint pattern: `POST /search`
- Execute envelope: `200 OK`
- Upstream status: `200`
- Execution id: `exec_e48e3d8b3f0142048a2978408a9c6c0f`
- Latency: `272.3 ms`

Sampled output:
- result count: `5`
- top title: `Best Observability Tools with AI-Powered Insights (2026) - Metoro`
- top URL: `https://metoro.io/blog/best-observability-tools-with-ai`

### Direct Tavily control
- HTTP status: `200 OK`
- Sampled output matched exactly:
  - result count: `5`
  - top title: `Best Observability Tools with AI-Powered Insights (2026) - Metoro`
  - top URL: `https://metoro.io/blog/best-observability-tools-with-ai`

## Comparison

| Dimension | Rhumb Resolve | Direct Tavily |
| --- | --- | --- |
| Reachability | Healthy | Healthy |
| Auth path | Rhumb-managed credential injection | Direct API key |
| Endpoint | Resolve → Tavily `/search` | Tavily `/search` |
| Output parity | Result count, top title, and top URL matched | Control truth |
| Investigation need | None — no execution bug reproduced | N/A |

## Public trust surface update

Published from this pass:
- Evidence id: `0352973a-cc2f-4045-9e5b-43dad9ba1447`
- Review id: `206fdbe9-2ab7-46a8-8d50-c648d75188cf`

Public depth moved:
- `tavily` runtime-backed reviews: **2 → 3**
- total reviews: **7 → 8**
- freshest public evidence: `2026-03-29T03:01:17.048617Z`

Post-publish callable audit:
- weakest runtime-backed depth stayed at **2**
- weakest bucket shrank from **10 → 9** providers

Artifacts:
- `rhumb/artifacts/callable-review-coverage-2026-03-28-live-now.json` (pass-start weakest-bucket state)
- `rhumb/artifacts/runtime-review-tavily-2026-03-28-current-pass.json`
- `rhumb/artifacts/callable-review-coverage-2026-03-28-post-pdl-tavily-current.json`

## Verdict

**Tavily remains healthy in production and now has deeper public runtime-backed coverage.**

Mission 1 is complete for this pass because the provider was selected from the live weakest bucket, executed through Rhumb Resolve, checked against direct control, and published with fresh public evidence.

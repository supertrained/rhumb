# Phase 3 runtime review — Tavily rerun

Date: 2026-03-27
Owner: Pedro / Keel runtime review loop
Priority: Mission 1 weakest-bucket rerun after telemetry + dogfood blockers remained external
Status: ✅ VERIFIED + PUBLISHED

## Why Tavily

The continuation brief and callable-review audit both pointed to the same next unblocked lane:
- telemetry MVP is already shipped
- real dogfood onboarding runs still need Tom timing
- Google AI config / verification is already done
- the clean next execution lane is therefore **Keel weakest-bucket runtime-review depth**

Before this pass, Tavily was still sitting in the weakest callable-review bucket at **1 runtime-backed review** alongside:
- `algolia`
- `apify`
- `apollo`
- `brave-search-api`
- `e2b`
- `people-data-labs`
- `replicate`
- `tavily`
- `unstructured`

Tavily was the cleanest next move because:
- it is callable in production
- it is read-only and low-side-effect
- the direct provider control is simple and already mirrored in Railway envs
- it supports clean same-input parity on a stable query

## Test setup

### Rhumb Resolve execution
- **Endpoint:** `POST /v1/capabilities/search.query/execute`
- **Capability:** `search.query`
- **Provider:** `tavily`
- **Credential mode:** `rhumb_managed`
- **Interface:** `runtime_review`
- **Estimate:** `GET /v1/capabilities/search.query/execute/estimate?provider=tavily&credential_mode=rhumb_managed`
- **Input:**
  ```json
  {
    "provider": "tavily",
    "credential_mode": "rhumb_managed",
    "params": {
      "query": "best AI agent observability tools",
      "search_depth": "basic",
      "max_results": 5
    },
    "interface": "runtime_review"
  }
  ```

### Direct provider control
- **Endpoint:** `POST https://api.tavily.com/search`
- **Auth:** live `RHUMB_CREDENTIAL_TAVILY_API_KEY` from Railway env
- **Input:** same query + search depth + result count

## Results

### Rhumb Resolve
- HTTP 200 from Rhumb
- Upstream status: **200**
- Execution id: `exec_245965a1dff24bafbc34d9ed26b55ec9`
- Estimate surface:
  - `cost_estimate_usd: 0.001`
  - `endpoint_pattern: POST /search`
  - `circuit_state: closed`
- Output highlights:
  - 5 results returned
  - top title: `Best Observability Tools with AI-Powered Insights (2026) - Metoro`
  - top URL: `https://metoro.io/blog/best-observability-tools-with-ai`
  - latency: `1346.4 ms`

### Direct Tavily control
- HTTP status: **200**
- Output highlights:
  - same 5-result ordering on the sampled response
  - top title matched exactly
  - top URL matched exactly
  - response time: `1.07 s`

## Comparison

| Dimension | Rhumb Resolve | Direct Tavily |
| --- | --- | --- |
| Reachability | Healthy | Healthy |
| Auth path | Rhumb-managed credential injection | Direct API key from Railway env |
| Endpoint | Resolve → Tavily `/search` | Tavily `/search` |
| Output parity | Same top result, top URL, and sampled ordering | Control truth |
| Investigation need | None — no execution bug reproduced | N/A |

## Public trust surface update

Because the rerun was clean, I published a fresh runtime-backed evidence + review pair.

Inserted records:
- **Evidence id:** `7abc9999-01f7-4c08-8329-9a7ca6cacfa8`
- **Review id:** `b04f1f48-3ac7-424b-b535-25e8a45215a7`

Public verification:
- `/v1/services/tavily/reviews` now shows the new top review:
  - **"Tavily: runtime rerun confirms search.query parity through Rhumb Resolve"**
- Tavily public review count increased from **6 → 7**
- Tavily runtime-backed review depth increased from **1 → 2**

## Coverage impact

After publishing the rerun, the callable-review audit moved the weakest bucket from **9 providers → 8 providers**.

Remaining weakest-bucket providers:
- `algolia`
- `apify`
- `apollo`
- `brave-search-api`
- `e2b`
- `people-data-labs`
- `replicate`
- `unstructured`

## Verdict

**Tavily is healthy in production and now has deeper public runtime-backed coverage.**

This pass did not surface a fresh Rhumb execution bug. The important outcome is that another weakest-bucket provider now has a second real production runtime proof on the public trust surface.

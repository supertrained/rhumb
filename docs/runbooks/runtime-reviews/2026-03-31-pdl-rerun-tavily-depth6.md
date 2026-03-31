# Runtime review loop — PDL rerun + Tavily depth 6

Date: 2026-03-31
Owner: Pedro / Keel runtime review loop

## Why this pass

Mission 0 remained mandatory: rerun canonical **People Data Labs** first after slug-normalization fix `94c8df8` and confirm that the live `people-data-labs` rail still works in production.

Mission 1 then had to take the callable provider with the fewest claim-safe runtime-backed reviews. The cache-busted audit showed a weakest depth of **5** across 9 providers, and **Tavily** was the stalest freshness candidate in that bucket.

## Mission 0 — PDL fix-verify rerun

### What was run
- Estimate:
  - `GET /v1/capabilities/data.enrich_person/execute/estimate?provider=people-data-labs&credential_mode=rhumb_managed`
- Managed execute:
  - `POST /v1/capabilities/data.enrich_person/execute?provider=people-data-labs&credential_mode=rhumb_managed`
- Direct control:
  - `GET https://api.peopledatalabs.com/v5/person/enrich`
- Input:
  - `profile=https://www.linkedin.com/in/satyanadella/`

### Result
- estimate: **200**
- Rhumb wrapper: **200**
- `provider_used`: **`people-data-labs`**
- Rhumb upstream: **402**
- direct provider control: **402**
- execution id: `exec_4cbb29633eed4e3583edf8723565c799`

### Conclusion
- canonical slug routing still works in production
- the old slug-normalization bug did **not** recur
- both lanes stopped at the same provider quota boundary (`account maximum / all matches used`)
- no new Rhumb execution-layer fix was required in this pass

Artifact:
- `artifacts/runtime-review-pass-20260331T192244Z-pdl-unstructured-depth4.json`

## Mission 1 — Tavily depth 5 → 6 freshness rerun

### Pre-pass coverage truth
Cache-busted audit before the pass:
- callable providers: **16**
- weakest claim-safe runtime depth: **5**
- weakest bucket size: **9**
- weakest bucket:
  - `algolia`
  - `apify`
  - `apollo`
  - `e2b`
  - `exa`
  - `firecrawl`
  - `replicate`
  - `tavily`
  - `unstructured`
- Tavily had the stalest public runtime evidence timestamp in that bucket.

### What was run
- Capability:
  - `search.query`
- Managed execute:
  - `POST /v1/capabilities/search.query/execute?provider=tavily&credential_mode=rhumb_managed`
- Direct control:
  - `POST https://api.tavily.com/search`
- Input:
  - `query=best AI agent observability tools`
  - `search_depth=basic`
  - `max_results=5`

### Result
Managed vs direct parity passed on:
- HTTP status: **200 / 200**
- `provider_used`: **`tavily`**
- upstream status: **200**
- result count: **5 / 5**
- top result title: **`Best Observability Tools with AI-Powered Insights (2026) - Metoro`**
- top result URL: **`https://metoro.io/blog/best-observability-tools-with-ai`**

Published trust rows:
- evidence: `a56e85cf-328e-4a27-9b82-b3e353a749d5`
- review: `f5d91e03-fa1a-4974-90c7-ebf85fce9433`
- execution id: `exec_bb92662002934bbcbd975f98dbad112b`

### Post-pass coverage truth
Cache-busted audit after publication:
- `tavily` moved **5 → 6** runtime-backed reviews
- weakest claim-safe runtime depth stayed **5**
- weakest bucket shrank **9 → 8**
- remaining weakest providers:
  - `algolia`
  - `apify`
  - `apollo`
  - `e2b`
  - `exa`
  - `firecrawl`
  - `replicate`
  - `unstructured`
- next freshness-ordered target is now **`firecrawl`**

## Structured runtime review verdict

### Rhumb execution
- succeeded
- preserved correct provider selection and auth injection
- returned the same top result and result count as direct control for the same live query

### Direct provider control
- succeeded
- matched managed execution on the observable result contract used for the review

### Comparison verdict
**Parity passed.** This is a clean runtime-backed review showing that Rhumb Resolve continues to execute Tavily correctly in production at current depth.

## Artifacts
- `artifacts/callable-review-coverage-2026-03-31-pre-tavily-depth6.json`
- `artifacts/runtime-review-pass-20260331T192244Z-pdl-unstructured-depth4.json`
- `artifacts/runtime-review-pass-20260331T192351Z-tavily-current-depth5.json`
- `artifacts/runtime-review-publication-2026-03-31-tavily-depth6.json`
- `artifacts/callable-review-coverage-2026-03-31-post-tavily-depth6.json`

## Verdict

PDL fix-verify remains clean: the slug fix still holds and the current blocker is provider quota, not Rhumb routing.
Tavily is now lifted above the weakest callable-review floor, and the freshness lane is ready to move to **Firecrawl** next.

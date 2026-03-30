# Runtime review loop — PDL fix-verify rerun + Tavily depth-5 publication

Date: 2026-03-30
Owner: Pedro / Keel runtime review loop
Priority: Mission 0 fix-verify first, then next weakest-bucket callable provider

## Mission 0 — PDL fix-verify rerun

The run started with the explicit instruction to re-check **People Data Labs** after the slug-normalization fix shipped in commit `94c8df8`.

### Why this rerun mattered

A previously-fixed Phase 3 failure only counts as complete if the canonical production path is re-verified after the fix. The point here was not to trust old notes; it was to prove the current production path still resolves correctly through Rhumb.

### Execution path exercised

- Capability: `data.enrich_person`
- Provider requested: `people-data-labs`
- Credential mode: `rhumb_managed`
- Input: `https://www.linkedin.com/in/satyanadella/`
- Estimate path: `GET /v1/capabilities/data.enrich_person/execute/estimate`
- Execute path: `POST /v1/capabilities/data.enrich_person/execute`
- Direct control: `GET https://api.peopledatalabs.com/v5/person/enrich`

### Result

- Estimate: **200**
- Rhumb-managed execute: **200**
- `provider_used`: **`people-data-labs`**
- Rhumb upstream status: **402**
- Direct provider control: **402**
- Artifact: `rhumb/artifacts/runtime-review-pass-20260330T190451Z-pdl-unstructured-depth4.json`

### Interpretation

This rerun did what it needed to do:
- the canonical slug still resolves correctly through Rhumb
- the old slug-normalization bug did **not** recur
- both Rhumb and direct control now stop at the same provider quota boundary

That means this pass did **not** surface a new execution-layer bug inside Rhumb. No slug-alias, auth-injection, credential-store, or execution-config repair was required for PDL in this run.

## Mission 1 — Tavily current-depth runtime rerun

After skipping PDL for the next-provider pick, the live callable inventory still showed **16 callable providers** and the callable review floor remained **4 runtime-backed reviews**.

Fresh pre-pass audit artifact:
- `rhumb/artifacts/callable-review-coverage-2026-03-30-pre-tavily-depth5.json`

Weakest callable bucket before the pass:
- `algolia`
- `apify`
- `apollo`
- `e2b`
- `exa`
- `firecrawl`
- `replicate`
- `tavily`
- `unstructured`

Tavily was taken as the next weakest-bucket provider for a fresh production parity check.

### Rhumb Resolve execution

- Capability: `search.query`
- Provider: `tavily`
- Credential mode: `rhumb_managed`
- Query: `best AI agent observability tools`
- `search_depth`: `basic`
- `max_results`: `5`

### Direct provider control

- Endpoint: `POST https://api.tavily.com/search`
- Auth: live `RHUMB_CREDENTIAL_TAVILY_API_KEY` from Railway env
- Input: same query, same depth, same result limit

### Runtime-review rail used

- Seeded temp org billing with `5000` cents
- Created temp review agent scoped to the temp org
- Granted only `tavily`
- Executed through the standard `X-Rhumb-Key` production rail
- Compared Rhumb-managed vs direct provider output
- Published evidence + review after parity passed
- Disabled the temp review agent after publish

## Results

### Rhumb Resolve

- Estimate: **200 OK**
- Execute: **200 OK**
- `provider_used`: `tavily`
- Upstream status: **200**
- Execution id: `exec_07cc638fedfd45afb7f2059f85c8e0aa`
- Result count: **5**
- Top result:
  - Title: `5 best AI agent observability tools for agent reliability in 2026`
  - URL: `https://www.braintrust.dev/articles/best-ai-agent-observability-tools-2026`

### Direct Tavily control

- HTTP status: **200**
- Result count: **5**
- Top result:
  - Title: `5 best AI agent observability tools for agent reliability in 2026`
  - URL: `https://www.braintrust.dev/articles/best-ai-agent-observability-tools-2026`

## Comparison

| Dimension | Rhumb Resolve | Direct Tavily |
| --- | --- | --- |
| Reachability | Healthy | Healthy |
| Auth path | Rhumb-managed body injection | Direct API key in request body |
| Result count | 5 | 5 |
| Top title parity | Exact match | Baseline |
| Top URL parity | Exact match | Baseline |
| Verdict | Working production integration | Provider API healthy |

## Public trust surface update

Published fresh runtime-backed artifacts:
- Evidence: `ce507979-3a11-4735-8b17-2049a10619e5`
- Review: `706e6eab-c8a0-4328-8726-13dc8394f1e9`

Artifacts:
- `rhumb/artifacts/runtime-review-pass-20260330T190954Z-tavily-current-depth5.json`
- `rhumb/artifacts/runtime-review-publication-2026-03-30-tavily-depth5.json`
- `rhumb/artifacts/callable-review-coverage-2026-03-30-pre-tavily-depth5.json`
- `rhumb/artifacts/callable-review-coverage-2026-03-30-post-tavily-depth5.json`

## Coverage impact

After the Tavily rerun:
- Tavily runtime-backed reviews moved **4 → 5**
- weakest callable runtime-backed depth stayed **4**
- weakest callable bucket shrank **9 providers → 8**

Remaining weakest-bucket callable providers:
- `algolia`
- `apify`
- `apollo`
- `e2b`
- `exa`
- `firecrawl`
- `replicate`
- `unstructured`

## Verdict

- **PDL fix-verify is confirmed clean on the canonical production path.**
- **Tavily is freshly re-verified in production at depth 5.**
- No new Rhumb execution-layer repair was required in this run because no managed/direct divergence appeared.

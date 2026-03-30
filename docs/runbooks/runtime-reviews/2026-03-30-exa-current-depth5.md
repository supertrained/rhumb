# Current-depth runtime review — Exa depth 5 publication

Date: 2026-03-30
Owner: Pedro / Keel runtime review loop
Priority: next stalest provider in the weakest callable-review bucket after Apollo

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
- Rhumb-managed execute wrapper: **200**
- `provider_used`: **`people-data-labs`**
- Rhumb upstream status: **402**
- Direct provider control: **402**
- Artifact: `rhumb/artifacts/runtime-review-pass-20260330T230551Z-pdl-unstructured-depth4.json`

### Interpretation

This rerun did what it needed to do:
- the canonical slug still resolves correctly through Rhumb
- the old slug-normalization bug did **not** recur
- both Rhumb and direct control now stop at the same provider quota boundary

That means this pass did **not** surface a new execution-layer bug inside Rhumb. No slug-alias, auth-injection, credential-store, or execution-config repair was required for PDL in this run.

## Mission 1 — Exa current-depth runtime rerun

Fresh live inventory check:
- `GET /v1/proxy/services` still showed **16 callable providers**
- artifact: `rhumb/artifacts/proxy-services-2026-03-30-current.json`

Fresh pre-pass coverage audit:
- weakest runtime-backed callable depth: **4**
- weakest bucket: `apify`, `e2b`, `exa`, `replicate`, `unstructured`
- artifact: `rhumb/artifacts/callable-review-coverage-2026-03-30-pre-current-run.json`

All five were tied on depth, so freshness decided the next move. **Exa** was the stalest provider in that weakest bucket, which made it the honest next target.

### Rhumb Resolve execution

- Capability: `search.query`
- Provider: `exa`
- Credential mode: `rhumb_managed`
- Query: `best AI agent observability tools`
- `numResults`: `3`

### Direct provider control

- Endpoint: `POST https://api.exa.ai/search`
- Auth: live `RHUMB_CREDENTIAL_EXA_API_KEY` from Railway production env
- Query: same query, same `numResults=3`
- Client note: sent with a normal browser-style `User-Agent`

### Runtime-review rail used

- temp org: `org_runtime_review_exa_20260330t230826z`
- seeded balance: `5000` cents
- temp review agent: `3a4cdd10-f356-4318-85a5-318bae674456`
- service grant: `exa` only
- temp access row: `f044a9cc-b106-43a2-b0cf-4accf638abaa`
- execution rail: normal `X-Rhumb-Key` path
- cleanup: temp review agent disabled after publish

## Results

### Rhumb Resolve
- Estimate: **200 OK**
- Estimated cost: **$0.001**
- Endpoint pattern: `POST /search`
- Execute: **200 OK**
- Execution id: `exec_4fc17d519ae343eb8250e6f9d8f189d6`
- Upstream status: **200**
- Result count: **3**
- Top result:
  - Title: `5 best AI agent observability tools for agent reliability in 2026 - Articles`
  - URL: `https://www.braintrust.dev/articles/best-ai-agent-observability-tools-2026`

### Direct Exa control
- Execute: **200 OK**
- Result count: **3**
- Top result:
  - Title: `5 best AI agent observability tools for agent reliability in 2026 - Articles`
  - URL: `https://www.braintrust.dev/articles/best-ai-agent-observability-tools-2026`

## Comparison

Parity checks passed on:
- exact result count (**3 = 3**)
- exact top title
- exact top URL
- exact top-3 URL ordering

Verdict: **production parity passed cleanly**.

## Public trust surface update

Published fresh runtime-backed rows:
- evidence: `af9da898-871f-4c52-9c10-a14cf4f78fc0`
- review: `56572a22-da8b-4cd8-861f-df5b416b4d5a`

Artifacts:
- `rhumb/artifacts/runtime-review-pass-20260330T230826Z-exa-current-depth5.json`
- `rhumb/artifacts/runtime-review-publication-2026-03-30-exa-depth5.json`
- `rhumb/artifacts/callable-review-coverage-2026-03-30-pre-current-run.json`
- `rhumb/artifacts/callable-review-coverage-2026-03-30-post-exa-depth5.json`
- `rhumb/artifacts/proxy-services-2026-03-30-current.json`

## Coverage impact

Post-publish audit confirmed:
- Exa runtime-backed review depth: **4 → 5**
- total published Exa reviews: **9 → 10**
- weakest callable-review bucket size: **5 → 4**
- weakest runtime-backed callable depth stays **4**, now across:
  - `apify`
  - `e2b`
  - `replicate`
  - `unstructured`

## Verdict

- **PDL fix-verify remains clean on the canonical production path.**
- **Exa is freshly re-verified in production at depth 5.**
- No new Rhumb execution-layer repair was required in this run because no managed/direct divergence appeared.

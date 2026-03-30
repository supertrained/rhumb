# Current-depth runtime review — Exa depth 4 publication

Date: 2026-03-30
Owner: Pedro OODA build loop
Priority: next stalest provider in the weakest callable-review bucket after Apollo

## Why Exa

This pass first re-checked the honest top blocker: whether a funded operator-controlled Base EOA with an exportable private key was available right now for `rhumb/scripts/wallet_prefund_dogfood.py`.

It still was not. No `RHUMB_DOGFOOD_WALLET_PRIVATE_KEY` surfaced in the active env, and current working notes still do not expose a funded exportable buyer wallet.

That kept the dogfood lane externally blocked, so the correct unblocked move was to keep shrinking the weakest callable-review bucket.

Fresh pre-pass audit confirmed:
- weakest runtime-backed callable depth: **3**
- weakest bucket size: **5**
- weakest providers: `apify`, `e2b`, `exa`, `replicate`, `unstructured`
- by freshness ordering, **Exa** was the stalest remaining weakest-bucket provider

## Test setup

### Rhumb Resolve execution
- Endpoint: `POST /v1/capabilities/search.query/execute`
- Provider: `exa`
- Credential mode: `rhumb_managed`
- Interface: `runtime_review`
- Query: `best AI agent observability tools`
- `numResults`: `3`

### Direct provider control
- Endpoint: `POST https://api.exa.ai/search`
- Auth: live `RHUMB_CREDENTIAL_EXA_API_KEY` from Railway production env
- Query: same query, same `numResults=3`
- Client note: sent with a normal browser-style `User-Agent`

### Runtime-review rail used
- temp org: `org_runtime_review_exa_20260330t102900z`
- seeded balance: `5000` cents
- temp review agent: `35b79f3f-008c-418f-9eff-cb6de4b7fac4`
- service grant: `exa` only
- temp access row: `4add9473-7064-4976-b78f-05baed1f444e`
- execution rail: normal `X-Rhumb-Key` path
- cleanup: temp review agent disabled after publish

## Results

### Rhumb Resolve
- Estimate: **200 OK**
- Estimated cost: **$0.001**
- Endpoint pattern: `POST /search`
- Execute: **200 OK**
- Execution id: `exec_ca6bd869392843c38efedd4686c123b0`
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
- evidence: `bbeaee84-b94f-4e93-9141-bdc5748d3c19`
- review: `a6b1ceb2-e64a-4d46-a338-7472f3ed9dc2`

Artifacts:
- `rhumb/artifacts/runtime-review-pass-20260330T102900Z-exa-current-depth4.json`
- `rhumb/artifacts/runtime-review-publication-2026-03-30-exa-depth4.json`
- `rhumb/artifacts/callable-review-coverage-2026-03-30-pre-exa-depth4.json`
- `rhumb/artifacts/callable-review-coverage-2026-03-30-post-exa-depth4.json`
- `rhumb/artifacts/exa-reviews-spotcheck-2026-03-30.json`

## Coverage impact

Post-publish audit confirmed:
- Exa runtime-backed review depth: **3 → 4**
- total published Exa reviews: **8 → 9**
- weakest callable-review bucket size: **5 → 4**
- weakest runtime-backed callable depth stays **3**, but now only across:
  - `apify`
  - `e2b`
  - `replicate`
  - `unstructured`

## Verdict

**Exa is now pushed above the weakest callable-review bucket.**

The honest blocker order remains unchanged:
1. funded exportable buyer-wallet proof for wallet-prefund dogfood is still externally blocked
2. Google AI wiring does **not** need reopening
3. the next best unblocked lane is another callable depth-expansion pass, with **Unstructured** now the stalest remaining weakest-bucket provider

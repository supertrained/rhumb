# Brave Search API — Phase 3 Runtime Review

Date: 2026-03-26
Operator: Pedro / Keel runtime loop
Status: passed after execution-layer fix

## Objective

Verify Brave Search in production through Rhumb Resolve, compare it against a direct provider control, and publish a runtime-backed review only if the live path succeeds.

## Pre-fix failure

Initial live checks exposed two separate execution-layer bugs inside Rhumb:

1. `GET /v1/capabilities/search.query/execute/estimate?provider=brave-search-api&credential_mode=rhumb_managed`
   returned a generic 503 because the estimate path was matching providers by exact slug and did not accept the canonical alias `brave-search-api` when the stored mapping still used proxy slug `brave-search`.
2. `POST /v1/capabilities/search.query/execute`
   reached Brave but returned upstream 422 because Rhumb forwarded logical field `query` instead of Brave's required `q` parameter.

Direct Brave control was healthy during the failure window, which isolated the issue to Rhumb rather than the provider.

## Investigation

Trace followed:
- capability id: `search.query`
- requested provider slug: `brave-search-api`
- execution mapping row: `brave-search`
- proxy normalization: canonical → proxy alias is valid
- direct provider auth: healthy with `X-Subscription-Token`
- direct provider execution: healthy

Files checked:
- `packages/api/routes/capability_execute.py`
- `packages/api/services/rhumb_managed.py`
- `packages/api/services/proxy_auth.py`
- `packages/api/services/proxy_credentials.py`
- `packages/api/routes/proxy.py`

Root causes:
- estimate path used exact slug equality instead of alias-aware matching
- managed Brave execution lacked a `query -> q` normalization step
- BYO auth wiring also lacked Brave's native auth header registration in `AuthInjector.AUTH_PATTERNS`

## Fix shipped

Commit: `7b7b44b` — `Fix Brave Search execution alias and param mapping`

Changes:
- made estimate provider selection alias-aware in `capability_execute.py`
- normalized Brave logical inputs (`query`, `numResults`) into provider-native params (`q`, `count`) in `rhumb_managed.py`
- registered Brave in `proxy_auth.py` with `X-Subscription-Token`
- added tests covering alias selection, Brave param mapping, and auth injection

## Live rerun

### Rhumb Resolve

- Estimate: HTTP 200
- Execute: HTTP 200
- Capability: `search.query`
- Provider used: `brave-search`
- Credential mode: `rhumb_managed`
- Upstream status: 200
- Top result: `8 LLM Observability Tools to Monitor & Evaluate AI Agents`
- Top URL: `https://www.langchain.com/articles/llm-observability-tools`

### Direct provider control

- Endpoint: Brave Search direct web search API
- Status: HTTP 200
- Top result: `8 LLM Observability Tools to Monitor & Evaluate AI Agents`
- Top URL: `https://www.langchain.com/articles/llm-observability-tools`

### Telemetry

`/v1/telemetry/recent` shows the successful Rhumb-managed Brave execution with:
- capability id `search.query`
- provider `brave-search`
- credential mode `rhumb_managed`
- upstream status `200`
- created at `2026-03-26T11:08:25.297208+00:00`

## Comparison

| Dimension | Rhumb Resolve | Direct Brave |
|---|---|---|
| Reachability | Healthy after fix | Healthy |
| Auth path | Rhumb-managed credential injection | Direct `X-Subscription-Token` |
| Output | Matched direct top result | Healthy |
| Telemetry | Execution row visible immediately | N/A |
| Operator conclusion | Working production integration after fix | Provider API healthy |

## Public trust surface update

After the live rerun:
- a new `runtime_verified` evidence record was inserted for Brave Search
- a new published review was created: **"Brave Search: Phase 3 runtime verification passed"**
- the review was linked to the evidence record in `review_evidence_links`

Review id:
- `1b504e13-3f81-4813-bdfa-99426c1fbcf8`

Evidence id:
- `7750319b-deb2-4f38-aa5d-d74f9159e24d`

## Truth-surface follow-up

Brave exposed a second slug-surface issue on the public read side: the catalog row and legacy reviews are stored under proxy slug `brave-search`, while public callers use canonical slug `brave-search-api`. A read-surface fallback was added so canonical review requests can surface proxy-backed evidence until the catalog is fully canonicalized.

## Phase 3 verdict

**Brave Search is Phase-3-verified in production.**

The direct provider is healthy, Rhumb-managed execution is healthy after the fix, telemetry captured the run, and the review/evidence spine now has live-backed proof.

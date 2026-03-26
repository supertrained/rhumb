# Phase 3 runtime review — Tavily

Date: 2026-03-25
Owner: Pedro / Keel runtime review loop
Priority: Phase 3 callable-provider verification

## Why Tavily

Google AI is still waiting on deploy/migration convergence in production, so the next unblocked lane was callable-provider runtime review depth. Tavily was a high-leverage search provider to verify because:
- it is already exposed through Rhumb Resolve for `search.query`
- it is part of the internal dogfood traffic mix
- a broken Tavily path would silently distort both dogfood confidence and runtime-backed review generation

## Test setup

### Rhumb Resolve execution
- Endpoint: `POST /v1/capabilities/search.query/execute`
- Provider: `tavily`
- Mode tested: `rhumb_managed`
- Input:
  - `query=best AI agent observability tools`
  - `search_depth=basic`
  - `max_results=5`

### Direct provider control
- Endpoint: `POST https://api.tavily.com/search`
- Auth: direct Tavily API key
- Input: same query / search depth / max results

## Results

### Rhumb Resolve
- Transport result: **HTTP 200 envelope**
- Upstream result: **422**
- Execution metadata:
  - `provider_used: tavily`
  - `credential_mode: rhumb_managed`
  - `execution_id` emitted normally
- Upstream error body:
  - `Field required` for `body.query`
- Observed behavior:
  - Rhumb injected the managed `api_key`
  - Rhumb did **not** forward the logical search inputs into the POST body
  - telemetry marked the execution as successful despite upstream 422 before the fix

### Direct Tavily control
- Result: **succeeded**
- HTTP status: **200**
- Response: 5 structured search results for the same query

## Comparison

| Dimension | Rhumb Resolve | Direct Tavily |
|---|---|---|
| Reachability | Reaches Tavily | Healthy |
| Request shape | Broken (drops query payload) | Correct |
| Output | 422 validation error | Structured results |
| Telemetry classification | Incorrectly treated as success before fix | N/A |
| Operator conclusion | Integration bug in Rhumb-managed POST payload handling | Provider API healthy |

## Root cause

Two product bugs were exposed:

1. **Managed POST payload merge bug**
   - public examples and dogfood calls send capability inputs via top-level `params`
   - for Rhumb-managed POST providers like Tavily, those logical inputs were not merged into the upstream JSON body
   - only the managed `api_key` was injected into the body, so Tavily received an incomplete request

2. **Execution success classification bug**
   - execution logging treated any `upstream_status < 500` as `success`
   - upstream 4xx provider failures were therefore logged as successful executions
   - this distorts telemetry and runtime-review confidence

## Fix shipped in repo

Shipped on 2026-03-25:
- `packages/api/services/rhumb_managed.py`
  - merge managed POST `params` into the upstream body before credential injection
  - classify success as `200 <= upstream_status < 400`
- `packages/api/routes/capability_execute.py`
  - align BYO / agent-vault success classification to the same `2xx/3xx only` rule
- tests added:
  - managed POST params→body regression coverage
  - 4xx execution classification / refund coverage

## Phase 3 verdict

**Tavily is not Phase-3-verified in production yet.**

The provider itself is healthy, but the production Rhumb Resolve path failed this runtime review. The repo-side fix is shipped; production must be re-run after deploy.

## Follow-up

1. Deploy the managed payload + success-classification fix.
2. Re-run `search.query` via `tavily` with the same payload.
3. Confirm:
   - upstream status returns 200
   - structured search results are returned
   - `capability_executions.success` is accurate for both success and failure cases
4. Once confirmed live, publish/update the runtime-backed review entry for Tavily.

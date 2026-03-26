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

## 10:45 PM production rerun confirmation

A fresh production rerun was executed after the fix landed live.

### Production rerun outcome
- Rhumb Resolve (`rhumb_managed`): **succeeded**
- HTTP envelope: **200**
- Upstream status: **200**
- Output: structured Tavily search results for the same query
- Execution logging: latest `capability_executions` row recorded `success=true`
- Provider health: `/v1/telemetry/provider-health` now shows `tavily` as **healthy** with the rerun as the latest sighting
- Public trust surface: `/v1/services/tavily/reviews` now includes a new **🟢 Runtime-verified** review row linked to the rerun evidence

### What changed in the diagnosis
The repo-side fix was the real issue. Once deployed, the managed Tavily path behaved correctly end-to-end:
- logical search inputs were forwarded into the upstream POST body
- Tavily returned a normal 200 with structured results
- telemetry / execution classification now matches reality

## Phase 3 verdict

**Tavily is now Phase-3-verified in production.**

The managed Rhumb Resolve path is live-clean again, and Tavily can stay in the callable-provider set without caveat.

## Follow-up

1. Keep Google AI as the next higher-priority verification lane once callable inventory catches up.
2. If Google AI is still absent from the live inventory, continue the next callable-provider runtime review with the thinnest runtime-backed coverage.
3. Investigate why live status surfaces show more callable providers than `GET /v1/proxy/services` currently exposes publicly.

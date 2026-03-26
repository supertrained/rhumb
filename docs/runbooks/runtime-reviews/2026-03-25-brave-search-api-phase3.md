# Phase 3 runtime review — Brave Search API

Date: 2026-03-25
Owner: Pedro / Keel runtime review loop
Priority: Phase 3 callable-provider verification

## Why Brave Search API

From live callable inventory and review coverage:
- `GET /v1/proxy/services` still exposes `brave-search-api` as callable
- `GET /v1/services/brave-search-api/reviews` currently returns **0 reviews**
- that makes Brave Search API the callable provider with the fewest visible runtime-backed reviews after the PDL rerun

## Test setup

### Rhumb Resolve execution
- Endpoint: `POST /v1/capabilities/search.query/execute`
- Provider: `brave-search-api`
- Credential mode: `rhumb_managed`
- Input: `q=Rhumb agent infrastructure`

### Direct provider control
- Endpoint: `GET https://api.search.brave.com/res/v1/web/search`
- Auth: direct Brave Search API key (`X-Subscription-Token`)
- Input: same query

## Results

### Rhumb Resolve
- Result: **succeeded**
- HTTP status: **200**
- Upstream status: **200**
- Response highlights:
  - returned structured Brave web results
  - top result title: **"Rhumb by supertrained | Glama"**

### Direct Brave control
- Result: **succeeded**
- HTTP status: **200**
- Response highlights:
  - returned structured Brave web results
  - top result title: **"Rhumb by supertrained | Glama"**

## Comparison

| Dimension | Rhumb Resolve | Direct Brave |
|---|---|---|
| Reachability | Healthy | Healthy |
| Status | 200 / upstream 200 | 200 |
| Query parity | Same top result | Same top result |
| Operator conclusion | Managed execution works | Provider API healthy |

## Phase 3 verdict

**Brave Search API is Phase-3-verified.**

Both Rhumb-managed execution and direct provider control returned successful structured search results for the same query, with matching top-result output.

## Follow-up

The remaining gap is not runtime execution. It is the **public review surface**:
- `/v1/services/brave-search-api/reviews` still shows `0` reviews despite successful runtime verification
- this should be investigated as a review/public-surface coverage issue rather than an execution issue

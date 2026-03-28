# Phase 3 runtime review — Brave Search rerun II (current pass)

Date: 2026-03-28
Owner: Pedro / Keel runtime review loop
Priority: Mission 1 weakest-bucket current-pass rerun after PDL Mission 0
Status: PASS — live production parity confirmed and fresh public evidence published

## Why Brave Search

I started from the live callable-review audit:
- artifact: `rhumb/artifacts/callable-review-coverage-2026-03-28-live-start.json`
- callable providers: **16**
- weakest runtime-backed depth at pass start: **2**

After skipping PDL because Mission 0 had already re-verified it in this run, I picked **Brave Search** from the remaining weakest-bucket providers because:
- it was tied at the minimum live runtime-backed depth
- it is read-only and low-side-effect
- it supports a clean same-input parity check between Rhumb Resolve and direct provider control

## Test setup

### Rhumb Resolve execution
- Endpoint: `POST /v1/capabilities/search.query/execute`
- Provider request: `brave-search-api`
- Resolved provider: `brave-search`
- Credential mode: `rhumb_managed`
- Interface: `runtime_review`
- Input:
  ```json
  {
    "provider": "brave-search-api",
    "credential_mode": "rhumb_managed",
    "params": {
      "query": "LLM observability tools",
      "numResults": 5
    },
    "interface": "runtime_review"
  }
  ```

### Direct provider control
- Endpoint: `GET https://api.search.brave.com/res/v1/web/search?q=LLM+observability+tools&count=5`
- Auth: direct `X-Subscription-Token` from live Railway env
- Input: same query + result count

## Results

### Rhumb Resolve
- HTTP 200
- Estimate endpoint returned 200
- Execution id: `exec_b1643f9fceb94b99aa2694653325524c`
- Result count: **5**
- Top title: `8 LLM Observability Tools to Monitor & Evaluate AI Agents`
- Top URL: `https://www.langchain.com/articles/llm-observability-tools`

### Direct Brave control
- HTTP 200
- Result count: **5**
- Top title matched exactly
- Top URL matched exactly

## Comparison

| Dimension | Rhumb Resolve | Direct Brave |
| --- | --- | --- |
| Reachability | Healthy | Healthy |
| Auth path | Rhumb-managed credential injection | Direct `X-Subscription-Token` |
| Provider slug path | `brave-search-api` normalized to `brave-search` | N/A |
| Output parity | Result count, top title, and top URL matched | Control truth |
| Investigation need | None — no execution bug reproduced | N/A |

## Public trust surface update

Fresh public evidence/review were written for this pass:
- Evidence id: `7f896226-46fb-4b3b-b7f8-7200fbe05744`
- Review id: `32499bd9-bf24-4f88-871b-e0f1c86b53e9`

Post-publish audit state:
- `brave-search-api` runtime-backed reviews: **3**
- total reviews: **8**
- freshest evidence: `2026-03-28T19:03:22.918767Z`

## Important follow-up note

The later post-publish callable audit surfaced an unrelated trust-surface anomaly where `slack` now appears at `0` runtime-backed reviews despite earlier passes showing `6`.

That did **not** affect the Brave execution path itself — Brave passed cleanly — but it means the coverage audit needs its own provenance cleanup before blanket coverage claims are repeated.

## Verdict

**Brave Search remains healthy in production, and this current-pass rerun confirmed live parity through Rhumb Resolve again.**

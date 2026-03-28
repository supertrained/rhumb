# Phase 3 runtime review — Exa rerun II

Date: 2026-03-27
Owner: Pedro / Keel runtime review loop
Priority: Mission 1 weakest-bucket rerun after PDL Mission 0

## Why Exa

After skipping PDL, the callable-review audit still showed Exa tied in the weakest public runtime-backed bucket at 1 review.

Exa remained a good next lane because:
- it is callable in production
- it is read-only and low-side-effect
- it supports clean same-input parity between Rhumb Resolve and direct provider control

## Test setup

### Rhumb Resolve
- Endpoint: `POST /v1/capabilities/search.query/execute`
- Provider: `exa`
- Credential mode: `rhumb_managed`
- Interface: `runtime_review`
- Input:
  - `query=best AI agent observability tools`
  - `numResults=3`

### Direct control
- Endpoint: `POST https://api.exa.ai/search`
- Auth: direct Exa API key
- Input: same query + result count

## Results

### Rhumb Resolve
- Result: **succeeded**
- HTTP envelope: **200**
- Upstream status: **200**
- Execution id: `exec_853936b4a2c24947ae1a973f720eb497`
- Output highlights:
  - 3 results returned
  - top title: `5 best AI agent observability tools for agent reliability in 2026 - Articles`
  - top URL: `https://www.braintrust.dev/articles/best-ai-agent-observability-tools-2026`

### Direct Exa control
- First attempt via Python `urllib`: **403 / Cloudflare 1010**
  - error: `browser_signature_banned`
  - diagnosis: control-client signature issue, not a provider-health signal
- Rerun via `curl` with a normal user-agent: **succeeded**
- Final HTTP status: **200**
- Final output matched Rhumb Resolve exactly on result count, top title, and top URL

## Comparison

| Dimension | Rhumb Resolve | Direct Exa |
| --- | --- | --- |
| Reachability | Healthy | Healthy after normal client signature |
| Auth path | Rhumb-managed credential injection | Direct Exa API key |
| Output parity | 3 results, top hit matched direct control | 3 results |
| Operator conclusion | Working production integration | Provider API healthy |

## Public trust surface update

Published after the rerun:
- Evidence id: `188c3f7f-062b-4f7e-88fc-ce5d669df126`
- Review id: `886dddbe-8ba3-48f3-b722-d85a73ae4f81`

Outcome:
- `/v1/services/exa/reviews` shows the new **🟢 Runtime-verified** review at the top
- callable-review coverage moved Exa from **1 → 2** public runtime-backed reviews

## Investigation outcome

No Rhumb execution bug surfaced.

The only failure mode encountered was on the **control client**, where Python `urllib` tripped a Cloudflare client-signature ban. Reissuing the same request with `curl` resolved it immediately, which confirms the provider itself was healthy and Rhumb was not the failing layer.

## Phase 3 verdict

**Exa is freshly re-verified in production and now has deeper public runtime-backed coverage.**

# Phase 3 runtime review — Firecrawl

Date: 2026-03-26
Owner: Pedro / Keel runtime review loop
Priority: Phase 3 callable-provider verification

## Why Firecrawl

Google AI is still not live in the callable inventory, so the next unblocked lane remained callable-provider runtime review depth.

Firecrawl was the cleanest next target because:
- it is already listed as callable in production status
- it still only had the older docs-backed review set on the public trust surface
- it exposes a simple same-input comparison path between Rhumb Resolve and direct provider control
- it is a useful proof point for Rhumb-managed scraping, which is one of the most practical near-term dogfood paths

## Test setup

### Rhumb Resolve execution
- Endpoint: `POST /v1/capabilities/scrape.extract/execute`
- Provider: `firecrawl`
- Credential mode: `rhumb_managed`
- Interface tag: `runtime_review`
- Input:
  - `url=https://example.com`

### Direct provider control
- Endpoint: `POST https://api.firecrawl.dev/v1/scrape`
- Auth: direct Firecrawl bearer token
- Input:
  - `url=https://example.com`
  - `formats=["markdown"]`

## Results

### Direct Firecrawl control
- Result: **succeeded**
- HTTP status: **200**
- Response highlights:
  - `success: true`
  - markdown content returned for Example Domain
  - metadata included `title: Example Domain`
  - upstream `statusCode: 200`

### Rhumb Resolve
- Result: **succeeded**
- Envelope status: **200**
- Upstream status: **200**
- Execution id: `exec_7055fe539a7c484eb7a4374995a93362`
- Telemetry row:
  - `success=true`
  - `provider_used=firecrawl`
  - `credential_mode=rhumb_managed`
  - `path=/v1/scrape`
  - `total_latency_ms=370.9`
  - `upstream_latency_ms=364.2`
- Output highlights:
  - structured upstream response returned inside the Rhumb execution envelope
  - markdown payload matched the direct-control test target
  - execution appeared immediately in `/v1/telemetry/recent`

## Comparison

| Dimension | Rhumb Resolve | Direct Firecrawl |
|---|---|---|
| Reachability | Healthy | Healthy |
| Auth path | Rhumb-managed credential injection | Direct bearer token |
| Output | Structured scrape payload with markdown | Structured scrape payload with markdown |
| Telemetry | Execution row visible immediately | N/A |
| Operator conclusion | Working production integration | Provider API healthy |

## Public trust surface update

After the live rerun:
- a new `runtime_verified` evidence record was inserted for Firecrawl
- a new published review was created: **"Firecrawl: Phase 3 runtime verification passed"**
- the review was linked to the evidence record in `review_evidence_links`
- `/v1/services/firecrawl/reviews` now shows a new **🟢 Runtime-verified** row at the top

Review id:
- `bfcaf8c0-80eb-4112-ac12-0b87e510689d`

Evidence id:
- `7984f0be-8bda-42e5-a154-4ef33f59b0c8`

## Supporting ops note

The previously stored dashboard API key in 1Password was stale. A fresh key was rotated from the authenticated dashboard session, used for the production verification, and then written back to the `Rhumb Launch Dashboard Key (Railway)` item so future internal loops stop failing on dead auth.

## Phase 3 verdict

**Firecrawl is Phase-3-verified in production.**

Direct provider runtime is healthy, Rhumb-managed execution is healthy, telemetry sees the call, and the public trust surface now reflects the live-backed proof.

## Follow-up

1. Continue the next callable-provider runtime review while Google AI remains absent from the live callable inventory.
2. Keep the callable inventory truth-surface mismatch on deck: `/v1/status` says 15 providers are callable, while `/v1/proxy/services` still needs reconciliation.
3. Prefer this same pattern for future reviews: live Rhumb-managed execution, direct provider control, telemetry confirmation, then public review/evidence publication.

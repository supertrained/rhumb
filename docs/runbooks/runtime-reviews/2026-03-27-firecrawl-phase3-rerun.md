# Phase 3 runtime review — Firecrawl rerun

Date: 2026-03-27
Owner: Pedro / Keel runtime review loop
Priority: Phase 3 callable-provider verification
Status: ✅ VERIFIED + PUBLISHED

## Why Firecrawl

I queried `GET /v1/proxy/services` for the current callable inventory, then checked review coverage across callable providers.

The lowest runtime-backed coverage bucket was still a large tie at **1 runtime-backed review** across:
- `apify`
- `apollo`
- `brave-search-api`
- `e2b`
- `exa`
- `firecrawl`
- `google-ai`
- `people-data-labs`
- `replicate`
- `tavily`
- `unstructured`

I skipped PDL for Mission 1 because Mission 0 had already rerun it this pass. From the remaining tied providers, Firecrawl was the cleanest next verification lane because it supports a deterministic same-input comparison on a stable public page.

## Test setup

### Rhumb Resolve execution
- **Endpoint:** `POST /v1/capabilities/scrape.extract/execute`
- **Capability:** `scrape.extract`
- **Provider:** `firecrawl`
- **Credential mode:** `rhumb_managed`
- **Estimate:** `GET /v1/capabilities/scrape.extract/execute/estimate?provider=firecrawl&credential_mode=rhumb_managed`
- **Input:**
  ```json
  {
    "provider": "firecrawl",
    "credential_mode": "rhumb_managed",
    "body": {
      "url": "https://example.com"
    },
    "interface": "runtime_review"
  }
  ```

### Direct provider control
- **Endpoint:** `POST https://api.firecrawl.dev/v1/scrape`
- **Auth:** direct Firecrawl bearer token
- **Input:**
  ```json
  {
    "url": "https://example.com",
    "formats": ["markdown"]
  }
  ```

## Results

### Rhumb Resolve
- HTTP 200 from Rhumb
- Upstream status: **200**
- Execution id: `exec_522eeabda4714359b4e8aef3f9866200`
- Estimate surface:
  - `endpoint_pattern: POST /v1/scrape`
  - `circuit_state: closed`
- Output highlights:
  - `success: true`
  - `metadata.title: Example Domain`
  - markdown prefix:
    ```
    # Example Domain

    This domain is for use in documentation examples without needing permission. Avoid use in operations.
    ```

### Direct Firecrawl control
- HTTP status: **200**
- Output highlights:
  - `success: true`
  - `metadata.title: Example Domain`
  - markdown prefix matched the Rhumb execution result exactly on the sampled output

## Comparison

| Dimension | Rhumb Resolve | Direct Firecrawl |
|---|---|---|
| Reachability | Healthy | Healthy |
| Auth path | Rhumb-managed credential injection | Direct bearer token |
| Endpoint | Resolve → Firecrawl `/v1/scrape` | Firecrawl `/v1/scrape` |
| Output parity | Example Domain title + markdown matched | Source of control truth |
| Investigation need | None — no failure reproduced | N/A |

## Public trust surface update

Because this rerun was clean, I published a fresh runtime-backed review and evidence record.

Inserted records:
- **Evidence id:** `0634777a-f8d9-4d26-acae-68c476c0d4bc`
- **Review id:** `a287a457-72c2-49e6-b9ed-bb4d99698028`

Public verification:
- `/v1/services/firecrawl/reviews` now shows the new top review:
  - **"Firecrawl: runtime rerun confirms scrape.extract parity through Rhumb Resolve"**
- Firecrawl public review count increased from **6 → 7**
- Firecrawl runtime-backed review depth increased from **1 → 2**

## Verdict

**Firecrawl is healthy in production and remains Phase-3-verified.**

This pass did not uncover an execution-layer bug, so Mission 0 investigation escalation was not needed. The important outcome is that the weakest review-coverage tier moved forward with another real runtime-backed proof.
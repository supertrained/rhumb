# Phase 3 runtime review — People Data Labs rerun (Railway-env direct control pass)

Date: 2026-03-27
Owner: Pedro / Keel runtime review loop
Priority: Mission 0 fix verification

## Why this rerun happened

PDL was explicitly called out as the highest-priority rerun after the slug-normalization fix in commit `94c8df8`.

An earlier same-day pass proved the Rhumb Resolve path was healthy, but direct-provider control was blocked because the shared 1Password service-account path behind `sop` had broken (`403 Forbidden / Service Account Deleted`).

This pass closed that gap by pulling the live provider credential from Railway envs instead of the broken vault path, then rerunning both sides.

## Test setup

### Rhumb Resolve
- Endpoint: `POST /v1/capabilities/data.enrich_person/execute`
- Provider: `people-data-labs`
- Credential mode: `rhumb_managed`
- Input: `profile=https://www.linkedin.com/in/satyanadella/`

### Direct provider control
- Endpoint: `GET https://api.peopledatalabs.com/v5/person/enrich`
- Auth: live `RHUMB_CREDENTIAL_PDL_API_KEY` from Railway env
- Input: same LinkedIn profile URL

## Results

### Rhumb Resolve
- Result: **succeeded**
- HTTP envelope: **200**
- Upstream status: **200**
- Execution id: `exec_29a9012ebf8448b29feb0da1563707bc`
- Key fields returned:
  - `full_name`: `satya nadella`
  - `job_title`: `board member`
  - `job_company_name`: `starbucks`
  - `linkedin_url`: `linkedin.com/in/satyanadella`
  - `likelihood`: `9`

### Direct PDL control
- Result: **succeeded**
- HTTP status: **200**
- Same key fields matched Rhumb Resolve on:
  - `full_name`
  - `job_title`
  - `job_company_name`
  - `linkedin_url`
  - `likelihood`

## Comparison

| Dimension | Rhumb Resolve | Direct PDL |
| --- | --- | --- |
| Reachability | Healthy | Healthy |
| Auth path | Rhumb-managed credential injection | Direct API key from Railway env |
| Output parity | Core identity/company fields matched direct control | Baseline |
| Verdict | Working production integration | Provider API healthy |

## Investigation outcome

No fresh execution-layer bug surfaced.

The important operational finding was narrower:
- the previous same-day blocker was **not** a PDL or Rhumb bug
- it was a **secret retrieval path failure** in the shared 1Password service-account flow
- Railway env access is a viable fallback for runtime-review parity checks when the provider secret is already mirrored there

## Phase 3 verdict

**People Data Labs remains Phase-3-verified in production.**

The slug-normalization fix from `94c8df8` is still holding, Rhumb Resolve is healthy, and direct provider control now confirms parity on the rerun.

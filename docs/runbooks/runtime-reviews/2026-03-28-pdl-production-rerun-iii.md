# Phase 3 runtime review — People Data Labs production rerun III

Date: 2026-03-28
Owner: Pedro / Keel runtime review loop
Priority: Mission 0 highest-priority reconfirm after slug-normalization fix
Status: PASS — live production rerun matched direct provider control and fresh public evidence was published

## Why this rerun happened

Mission 0 for this pass was explicit: **rerun PDL now** because the slug-normalization fix shipped in commit `94c8df8`, and a passing historical note does not satisfy the fix-verify loop.

This run rechecked the full live path again:
- capability → `data.enrich_person`
- requested provider → `people-data-labs`
- managed credential injection → live PDL key through Rhumb-managed execution
- upstream execution → `GET /v5/person/enrich`
- direct control → same PDL endpoint with the same input

## Test setup

### Rhumb Resolve execution
- Endpoint: `POST /v1/capabilities/data.enrich_person/execute`
- Estimate: `GET /v1/capabilities/data.enrich_person/execute/estimate?provider=people-data-labs&credential_mode=rhumb_managed`
- Provider: `people-data-labs`
- Credential mode: `rhumb_managed`
- Interface: `runtime_review`
- Input:
  ```json
  {
    "profile": "https://www.linkedin.com/in/satyanadella/"
  }
  ```

### Direct provider control
- Endpoint: `GET https://api.peopledatalabs.com/v5/person/enrich`
- Auth: direct `X-Api-Key`
- Input: same LinkedIn profile URL

### Runtime-review rail used
- Seeded a temporary internal org wallet with execution headroom
- Created a temporary review agent via the live admin-agent route
- Granted `people-data-labs` and proxy alias `pdl`
- Executed through the standard `X-Rhumb-Key` rail
- Published evidence + review only after parity passed

## Results

### Rhumb Resolve
- Estimate: `200 OK`
- Cost estimate: `$0.10`
- Circuit state: `closed`
- Endpoint pattern: `GET /v5/person/enrich`
- Execute envelope: `200 OK`
- Upstream status: `200`
- Execution id: `exec_562bb0fdd3c345a780019ee5f8bded34`
- Latency: `814.0 ms`

Sampled returned fields:
- `full_name`: `satya nadella`
- `job_title`: `board member`
- `job_company_name`: `starbucks`
- `linkedin_url`: `linkedin.com/in/satyanadella`

### Direct PDL control
- HTTP status: `200 OK`
- Sampled returned fields matched exactly:
  - `full_name`: `satya nadella`
  - `job_title`: `board member`
  - `job_company_name`: `starbucks`
  - `linkedin_url`: `linkedin.com/in/satyanadella`

## Comparison

| Dimension | Rhumb Resolve | Direct PDL |
| --- | --- | --- |
| Reachability | Healthy | Healthy |
| Auth path | Rhumb-managed credential injection | Direct `X-Api-Key` |
| Slug path | Canonical `people-data-labs` still resolves cleanly | N/A |
| Output parity | Sampled enrichment fields matched exactly | Control truth |
| Investigation outcome | No fresh execution bug reproduced | N/A |

## Public trust surface update

Published fresh runtime-backed artifacts from this pass:
- Evidence id: `c33a8cb9-b0c8-40a4-90bf-f8e978ebc6c9`
- Review id: `e3cd273f-be68-4404-a347-03726abc09b1`

Public depth moved:
- `people-data-labs` runtime-backed reviews: **4 → 5**
- total reviews: **9 → 10**
- freshest public evidence: `2026-03-29T03:01:13.126252Z`

Artifact bundle:
- `rhumb/artifacts/runtime-review-pdl-2026-03-28-reconfirm-iii.json`

## Verdict

**The PDL slug-normalization fix from `94c8df8` still holds in production.**

Mission 0 is complete for this pass because it ended with a fresh production rerun, direct-provider parity, and new public evidence — not just a note that an earlier rerun once passed.

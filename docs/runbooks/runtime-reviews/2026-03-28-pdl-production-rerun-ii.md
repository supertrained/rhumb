# Phase 3 runtime review — People Data Labs production rerun II

Date: 2026-03-28
Owner: Pedro / Keel runtime review loop
Priority: Mission 0 highest-priority reconfirm after slug-normalization fix
Status: PASS — live production rerun matched direct provider control and fresh public evidence was published

## Why this rerun happened

The standing instruction for this pass was explicit: **rerun PDL now** because the slug-normalization fix shipped in commit `94c8df8` and Mission 0 required fresh live confirmation rather than relying on earlier same-day evidence.

This pass therefore rechecked the full live execution path:
- capability → `data.enrich_person`
- requested provider → `people-data-labs`
- provider normalization → canonical PDL slug
- managed credential injection → live Railway-mirrored PDL key
- upstream execution → People Data Labs `GET /v5/person/enrich`

## Test setup

### Rhumb Resolve execution
- Endpoint: `POST /v1/capabilities/data.enrich_person/execute`
- Provider: `people-data-labs`
- Credential mode: `rhumb_managed`
- Interface: `runtime_review`
- Input:
  - `profile=https://www.linkedin.com/in/satyanadella/`

### Direct provider control
- Endpoint: `GET https://api.peopledatalabs.com/v5/person/enrich`
- Auth: direct `X-Api-Key` from live Railway env
- Input: same LinkedIn profile URL

## Results

### Rhumb Resolve
- HTTP 200
- Estimate endpoint also returned 200
- Execution succeeded through the managed rail
- Returned fields:
  - `full_name`: `satya nadella`
  - `job_title`: `board member`
  - `job_company_name`: `starbucks`
  - `linkedin_url`: `linkedin.com/in/satyanadella`

### Direct PDL control
- HTTP 200
- Returned the same sampled fields:
  - `full_name`: `satya nadella`
  - `job_title`: `board member`
  - `job_company_name`: `starbucks`
  - `linkedin_url`: `linkedin.com/in/satyanadella`

## Comparison

| Dimension | Rhumb Resolve | Direct PDL |
| --- | --- | --- |
| Reachability | Healthy | Healthy |
| Auth path | Rhumb-managed credential injection | Direct `X-Api-Key` |
| Slug path | `people-data-labs` normalized correctly to live PDL execution | N/A |
| Output parity | Matched sampled enrichment fields exactly | Control truth |
| Investigation outcome | No fresh execution bug reproduced | N/A |

## Public trust surface update

Because this rerun was clean, I published a fresh runtime-backed evidence + review pair tied to this exact pass:
- Evidence id: `32ed4609-4156-44ef-9e35-78ac1f546ae3`
- Review id: `b4524fc7-749a-41a2-9623-49a4ed7f03f6`

Post-publish audit state:
- `people-data-labs` runtime-backed reviews: **4**
- total reviews: **9**
- freshest evidence: `2026-03-28T19:04:18.699919Z`

## Verdict

**The PDL slug-normalization fix from `94c8df8` is confirmed live in production.**

Mission 0 is complete for this provider because the pass ended with re-verification and fresh public evidence, not just a note saying the provider previously failed.

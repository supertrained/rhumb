# People Data Labs — Phase 3 runtime rerun after slug-normalization fix

Date: 2026-03-26
Operator: Pedro / Keel runtime loop
Status: passed

## Why this rerun happened

PDL had an execution-layer failure boundary on 2026-03-25: direct provider control worked, but Rhumb Resolve returned plain 503 for `data.enrich_person`. Commit `94c8df8` shipped a slug-normalization fix. This rerun was the required fix-verify step to confirm the bug is actually gone in production.

## Inputs

- Capability: `data.enrich_person`
- Provider: `people-data-labs`
- Credential mode: `rhumb_managed`
- Test input: `profile=https://www.linkedin.com/in/satyanadella/`

## Rhumb execution

### Estimate
- Endpoint: `GET /v1/capabilities/data.enrich_person/execute/estimate?provider=people-data-labs&credential_mode=rhumb_managed`
- Result: **200 OK**
- Request id: `a40db4fd-47a3-4244-af3e-2ca3bc51147f`

### Execute
- Endpoint: `POST /v1/capabilities/data.enrich_person/execute`
- Result: **200 OK**
- Execution id: `exec_086ed3acba7c47228db6f0af7d7f4435`
- Upstream status: `200`
- Returned a structured enrichment payload for the requested LinkedIn profile

## Direct provider control

- Endpoint: `GET https://api.peopledatalabs.com/v5/person/enrich?profile=...`
- Result: **200 OK**
- Returned the expected PDL enrichment object for the same profile input

## Comparison

| Check | Rhumb | Direct PDL | Verdict |
|---|---:|---:|---|
| HTTP status | 200 | 200 | Match |
| Request shape | profile query param | profile query param | Match |
| Payload class | person enrichment object | person enrichment object | Match |

## Root-cause verdict

The earlier failure is no longer reproducible. The `pdl -> people-data-labs` slug-normalization fix from commit `94c8df8` is confirmed live in production.

## Trust-surface action

- Superseded stale failure reviews:
  - `7c2a9d81-97b1-48e1-aa0d-84b3394a07f2`
  - `acaed3ae-eaa2-42f7-9aea-f92fd244f763`
- Published fresh runtime evidence: `762965fd-ea1c-4bb9-9fa6-375831c46437`
- Published fresh runtime review: `f56d4a08-7ac2-4e2a-9b15-914dcdd209e7`

## Operator takeaway

PDL is back in the healthy bucket. The right conclusion is no longer "provider healthy, Rhumb broken" — it is now "fix verified, Rhumb and direct control agree."
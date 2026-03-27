# Runtime Review: People Data Labs production rerun — 2026-03-26

Date: 2026-03-26
Operator: Pedro / Keel runtime loop
Status: ✅ VERIFIED

## Why this rerun happened

Cron directive required a fresh post-fix production check after the slug-normalization work shipped in commit `94c8df8`.

## What I tested

### Rhumb Resolve
- **Estimate:** `GET /v1/capabilities/data.enrich_person/execute/estimate?provider=people-data-labs&credential_mode=rhumb_managed`
- **Execute:** `POST /v1/capabilities/data.enrich_person/execute`
- **Capability:** `data.enrich_person`
- **Provider:** `people-data-labs`
- **Credential mode:** `rhumb_managed`
- **Payload:** `{ "body": { "profile": "https://www.linkedin.com/in/satyanadella/" } }`

### Direct control
- **Endpoint:** `GET https://api.peopledatalabs.com/v5/person/enrich?profile=https://www.linkedin.com/in/satyanadella/`
- **Auth:** direct PDL API key

## Results

### Resolve result
- HTTP 200 from Rhumb
- Upstream status: **200**
- Execution id: `exec_1b800e3cb18b4cf1a15b94bd55ab4522`
- Returned identity matched direct control:
  - `full_name`: `satya nadella`
  - `job_title`: `board member`
  - `job_company_name`: `starbucks`
  - `linkedin_url`: `linkedin.com/in/satyanadella`
  - `likelihood`: `9`

### Direct result
- HTTP 200 direct from PDL
- Same person payload and key business fields as Resolve

## Investigation note

My first fresh rerun attempt failed with upstream 400 because I accidentally sent the payload under `input` instead of the route’s expected `body` field. I traced `packages/api/routes/capability_execute.py` and confirmed the execute contract is `body`/`params`, not `input`. After correcting the request shape, Resolve passed cleanly.

This means:
- the **slug normalization fix is holding in production**
- there is **no remaining PDL execution-layer bug** on the live happy path tested here
- the earlier failure was client-side request-shape error, not a regression in Rhumb

## Conclusion

PDL remains live after the normalization fix. Mission 0 is satisfied: the provider was rerun in production, parity was checked against direct control, and the fix holds.
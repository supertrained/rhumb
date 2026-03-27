# People Data Labs — post-fix production confirmation

Date: 2026-03-26
Operator: Pedro / Keel runtime loop
Status: passed

## Why this rerun happened

The Keel cron explicitly required a fresh Mission 0 check after the slug-normalization fix shipped in commit `94c8df8`. PDL had already been rerun earlier in the day, but this run confirms the production path is still healthy now.

## Inputs

- Capability: `data.enrich_person`
- Provider: `people-data-labs`
- Credential mode: `rhumb_managed`
- Test input: `profile=https://www.linkedin.com/in/satyanadella/`

## Rhumb execution

### Estimate
- Endpoint: `GET /v1/capabilities/data.enrich_person/execute/estimate?provider=people-data-labs&credential_mode=rhumb_managed`
- Result: **200 OK**

### Execute
- Endpoint: `POST /v1/capabilities/data.enrich_person/execute`
- Result: **200 OK**
- Execution id: `exec_52826d8ae95d495b9fdf59f0c54c08bf`
- Upstream status: `200`
- Returned nested PDL enrichment payload under `upstream_response.data`
- Key fields matched direct control:
  - `full_name`: `satya nadella`
  - `job_title`: `board member`
  - `job_company_name`: `starbucks`
  - `linkedin_url`: `linkedin.com/in/satyanadella`
  - `likelihood`: `9`

## Direct provider control

- Endpoint: `GET https://api.peopledatalabs.com/v5/person/enrich?profile=...`
- Result: **200 OK**
- Returned the same enrichment identity for the same LinkedIn profile

## Comparison

| Check | Rhumb | Direct PDL | Verdict |
|---|---:|---:|---|
| HTTP status | 200 | 200 | Match |
| Upstream status | 200 | 200 | Match |
| Payload class | person enrichment | person enrichment | Match |
| Key identity fields | Satya Nadella / Starbucks | Satya Nadella / Starbucks | Match |

## Root-cause verdict

No regression is present. The canonical `people-data-labs` slug continues to normalize correctly through the live execution path, auth injection, and upstream request routing.

## Operator takeaway

Mission 0 remains closed: the `94c8df8` fix still holds in production, and PDL stays in the healthy callable bucket.

# Runtime review — People Data Labs production rerun

Date: 2026-03-27
Owner: Pedro / Keel runtime review loop
Status: ✅ VERIFIED

## Why this rerun happened

Mission 0 required an immediate post-fix production confirmation for PDL after the slug-normalization repair shipped in commit `94c8df8`.

I checked the active working context first:
- `memory/working/continuation-brief.md`
- `memory/2026-03-27.md`

That context showed recent execution-layer fixes and confirmed PDL was the top-priority rerun lane for this cron pass.

## What I tested

### Rhumb Resolve
- **Estimate:** `GET /v1/capabilities/data.enrich_person/execute/estimate?provider=people-data-labs&credential_mode=rhumb_managed`
- **Execute:** `POST /v1/capabilities/data.enrich_person/execute`
- **Capability:** `data.enrich_person`
- **Provider:** `people-data-labs`
- **Credential mode:** `rhumb_managed`
- **Payload:**
  ```json
  {
    "provider": "people-data-labs",
    "credential_mode": "rhumb_managed",
    "body": {
      "profile": "https://www.linkedin.com/in/satyanadella/"
    },
    "interface": "mcp"
  }
  ```

### Direct control
- **Endpoint:** `GET https://api.peopledatalabs.com/v5/person/enrich?profile=https://www.linkedin.com/in/satyanadella/`
- **Auth:** direct PDL API key

## Results

### Resolve result
- HTTP 200 from Rhumb
- Upstream status: **200**
- Execution id: `exec_940910ddb7ec4bda9629c2e1c89fe59c`
- Estimate surface was healthy:
  - `cost_estimate_usd: 0.1`
  - `endpoint_pattern: GET /v5/person/enrich`
  - `circuit_state: closed`
- Returned person payload matched the direct control on the core business fields:
  - `full_name: satya nadella`
  - `job_title: board member`
  - `job_company_name: starbucks`
  - `linkedin_url: linkedin.com/in/satyanadella`

### Direct result
- HTTP 200 direct from PDL
- `likelihood: 9`
- `data.full_name: satya nadella`
- `data.job_title: board member`
- `data.job_company_name: starbucks`
- `data.linkedin_url: linkedin.com/in/satyanadella`

## Investigation outcome

This rerun did **not** reproduce the old failure. Because Resolve and the direct provider control both succeeded, there was no live execution-layer regression to chase on this pass.

Operational conclusion:
- `people-data-labs` still resolves correctly through the production execution path
- the slug-normalization fix from `94c8df8` is holding
- no additional alias/auth/env mapping repair was required during this run

## 8:07 AM follow-up spot-check

A second production spot-check was run later in the morning to make sure the earlier pass was not a one-off.

### Follow-up Resolve result
- HTTP 200 from Rhumb
- Upstream status: **200**
- Execution id: `exec_c13e3ae41e2f461a9d3e452c94980729`
- Returned `likelihood: 9`

### Follow-up direct result
- HTTP 200 direct from PDL
- Returned `likelihood: 9`

The second pass matched the first: no regression, no alias break, and no evidence of a stale deploy.

## Verdict

**PDL is confirmed healthy in production after the slug-normalization fix.**

Mission 0 is satisfied for this run: the provider was rerun, direct control was checked, parity held, and there is no remaining live failure to investigate.
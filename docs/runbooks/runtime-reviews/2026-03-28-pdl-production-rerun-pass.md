# Production runtime review — People Data Labs rerun

Date: 2026-03-28
Owner: Pedro / Keel runtime review loop
Priority: Mission 0 fix verification

## Why PDL

This rerun was mandatory because `people-data-labs` had a production slug-normalization issue and a fix was shipped in commit `94c8df8`.

Mission 0 for this loop was explicit: do not just trust the fix-in-the-abstract — rerun Phase 3 against production and confirm the lane is actually healthy now.

## Test setup

### Rhumb Resolve execution
- Endpoint: `POST /v1/capabilities/data.enrich_person/execute`
- Provider: `people-data-labs`
- Credential mode: `rhumb_managed`
- Input:
  ```json
  {
    "profile": "https://www.linkedin.com/in/satyanadella/"
  }
  ```

### Direct provider control
- Endpoint: `GET https://api.peopledatalabs.com/v5/person/enrich`
- Auth: live `RHUMB_CREDENTIAL_PDL_API_KEY` from Railway env
- Query: same `profile` input

### Runtime-review rail used
- Seeded a temporary internal org wallet with `5000` cents for execution headroom
- Created a temporary review agent via the live admin-agent route
- Granted `people-data-labs` and the proxy alias `pdl`
- Executed through the normal `X-Rhumb-Key` rail
- Published evidence + review after parity passed

## Results

### Rhumb Resolve
- Capability: `data.enrich_person`
- Result: **succeeded**
- HTTP status: **200**
- Key returned fields:
  - `full_name`: `Satya Nadella`
  - `job_title`: `Chairman and CEO`
  - `job_company_name`: `Microsoft`
  - `linkedin_url`: `linkedin.com/in/satyanadella`

### Direct PDL control
- Result: **succeeded**
- HTTP status: **200**
- Same key returned fields matched:
  - `full_name`: `Satya Nadella`
  - `job_title`: `Chairman and CEO`
  - `job_company_name`: `Microsoft`
  - `linkedin_url`: `linkedin.com/in/satyanadella`

## Comparison

| Dimension | Rhumb Resolve | Direct PDL |
| --- | --- | --- |
| Reachability | Healthy | Healthy |
| Auth path | Rhumb-managed API-key injection | Direct API key from Railway env |
| Slug path | Canonical `people-data-labs` | Native provider endpoint |
| Output parity | Key identity fields matched | Baseline |
| Verdict | Working production integration | Provider API healthy |

## Investigation outcome

Mission 0 asked for investigation if the rerun failed.

It did **not** fail.

That means:
- no fresh execution-layer bug reproduced
- no new alias, auth-injection, credential-store, or execution-config fix was required in this pass
- the `94c8df8` slug-normalization fix now has another production confirmation

## Public trust surface update

Published fresh runtime-backed artifacts:
- Evidence: `97d553d7-ec32-42de-a70d-c4f0c8ad9415`
- Review: `7ead7a09-89bf-4ba2-bf4c-c4f75f966e03`

Public depth moved:
- PDL runtime-backed reviews: **2 → 3**
- Total published reviews: **7 → 8**

Fresh artifact bundle:
- `rhumb/artifacts/runtime-review-pdl-2026-03-28.json`

## Verdict

**People Data Labs is re-verified in production after the slug-normalization fix.**

The provider passed through Rhumb Resolve and through direct provider control with matching key identity fields, so Mission 0 is complete for PDL on this loop.

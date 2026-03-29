# Current-pass runtime review — PDL reconfirm + Unstructured weakest-bucket rerun

Date: 2026-03-29
Owner: Pedro / Keel runtime review loop

## Mission 0 — PDL fix-verify rerun

The top priority for this pass was an honest fresh production rerun for **People Data Labs** after the earlier execute-envelope parsing repair.

I re-used the same shorthand execute shape that previously exposed the bug:
- `POST /v1/capabilities/data.enrich_person/execute?provider=people-data-labs&credential_mode=rhumb_managed`
- raw provider-native JSON body:
  ```json
  {
    "profile": "https://www.linkedin.com/in/satyanadella/"
  }
  ```

### Results

#### Rhumb Resolve
- estimate: **200 OK**
- provider used: **`people-data-labs`**
- credential mode: **`rhumb_managed`**
- upstream status: **200**
- execution id: `exec_55f33f05dd7248d0afb125f0bbf5b784`

Matched verification fields:
- `full_name`: `satya nadella`
- `job_title`: `board member`
- `job_company_name`: `starbucks`
- `linkedin_url`: `linkedin.com/in/satyanadella`

#### Direct PDL control
- endpoint: `GET https://api.peopledatalabs.com/v5/person/enrich`
- status: **200**
- returned the same values for the same fields

### Mission 0 verdict

**The fix still holds in production.**

There was no fresh reroute bug, no slug normalization regression, and no auth-injection break. The live execute path honored the requested provider and matched direct provider control.

Published fresh proof:
- Evidence: `b99dbfef-5394-4e19-b60a-a2870c1cf76e`
- Review: `b78ebc1e-e897-4975-9b64-9ae647af1eed`

Coverage impact:
- `people-data-labs` runtime-backed reviews: **7 → 8**

## Mission 1 — weakest-bucket callable provider pass

### Provider selection

A fresh callable audit at the top of the pass showed the weakest runtime-backed callable bucket at **2 reviews across 4 providers**:
- `apify`
- `e2b`
- `replicate`
- `unstructured`

I picked **Unstructured** because it had the oldest freshest runtime evidence in that weakest bucket, and its direct-control parity path is deterministic.

### Test setup

#### Rhumb Resolve
- Estimate: `GET /v1/capabilities/document.parse/execute/estimate?provider=unstructured&credential_mode=rhumb_managed`
- Execute: `POST /v1/capabilities/document.parse/execute?provider=unstructured&credential_mode=rhumb_managed`
- Input: same text file upload through the fixed shorthand execute path
- File: `runtime-review-unstructured.txt`
- Strategy: `fast`

#### Direct provider control
- Endpoint: `POST https://api.unstructuredapp.io/general/v0/general`
- Auth: live Unstructured API key from Railway env
- Input: same text file, same `strategy=fast`

### Results

#### Rhumb Resolve
- estimate: **200 OK**
- execute wrapper status: **200**
- upstream status: **200**
- execution id: `exec_0ab48d52211e44dd8c82ceee1d8a4c4d`
- provider used: **`unstructured`**
- output element types:
  - `Title`
  - `NarrativeText`
- element count: **2**

#### Direct Unstructured control
- HTTP status: **200**
- output element types:
  - `Title`
  - `NarrativeText`
- element count: **2**

### Verdict

**Unstructured passed with exact parity on element types and element count.**

Published fresh proof:
- Evidence: `6303828a-8b5d-4297-9a09-c666895d56c2`
- Review: `65dcc241-1877-4062-acb8-3fcf46322dd6`

Coverage impact:
- `unstructured` runtime-backed reviews: **2 → 3**
- weakest callable bucket shrank **4 providers → 3 providers**

Remaining weakest bucket:
- `apify`
- `e2b`
- `replicate`

## Mission 2 — discovery expansion

After the verification work, I expanded the **geolocation** category.

Why geolocation:
- live category depth was only **5** providers
- agents frequently need IP-to-location, timezone, routing context, localization, and fraud/risk enrichment
- the current surface was too thin relative to real agent demand

Added services:
- `ipregistry`
- `ip2location`
- `ipapi`
- `bigdatacloud`
- `db-ip`

Discovery artifacts:
- `packages/api/migrations/0118_geolocation_expansion.sql`
- `docs/runbooks/discovery-expansion/2026-03-29-geolocation-expansion.md`

Best Phase 0 wedge:
- `network.ip_geolocate`
- `timezone.lookup`

Best first provider target:
- **IPregistry**

## Artifact bundle

- `artifacts/callable-review-coverage-2026-03-29-pre-loop-20260329T190837Z.json`
- `artifacts/runtime-review-pass-20260329T191209Z-pdl-unstructured-current.json`
- `artifacts/callable-review-coverage-2026-03-29-post-loop-20260329T191209Z.json`

## Final verdict

This pass completed all three missions in order:
1. **PDL was rerun fresh on the fixed production execute path and still matches direct control**
2. **Unstructured received the next weakest-bucket runtime-backed review with direct-provider parity**
3. **Geolocation discovery depth expanded by five services with a clear Phase 0 wedge**

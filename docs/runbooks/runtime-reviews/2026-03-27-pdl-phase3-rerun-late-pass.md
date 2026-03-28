# People Data Labs Phase 3 rerun — late production confirmation

Date: 2026-03-27
Owner: Pedro / Keel runtime review loop
Priority: Mission 0 fix-verify loop
Status: ✅ passed in production

## Why this rerun happened

Tom's directive for the Keel loop is explicit: when a Phase 3 failure has a shipped fix, rerun it in production and do not stop at "logged failure." PDL had a slug-normalization repair shipped in commit `94c8df8`, so this run started by re-verifying that fix live.

## Working contract

- **Capability:** `data.enrich_person`
- **Provider requested:** `people-data-labs`
- **Credential mode:** `rhumb_managed`
- **Input:** `profile=https://www.linkedin.com/in/satyanadella/`
- **Rhumb estimate:** `GET /v1/capabilities/data.enrich_person/execute/estimate?provider=people-data-labs&credential_mode=rhumb_managed`
- **Rhumb execute:** `POST /v1/capabilities/data.enrich_person/execute`
- **Direct control:** `GET https://api.peopledatalabs.com/v5/person/enrich?profile=...`

## Results

### Rhumb Resolve
- **Envelope status:** `200 OK`
- **Upstream status:** `200`
- **Execution id:** `exec_0db51cb37c4f42f58e3bc64c35632463`
- **Latency:** `879.1 ms`
- **Provider used:** `people-data-labs`

Core returned fields:
- `full_name`: `satya nadella`
- `job_title`: `board member`
- `job_company_name`: `starbucks`
- `linkedin_url`: `linkedin.com/in/satyanadella`
- `likelihood`: `9`

### Direct provider control
- **HTTP:** `200 OK`

Core returned fields:
- `full_name`: `satya nadella`
- `job_title`: `board member`
- `job_company_name`: `starbucks`
- `linkedin_url`: `linkedin.com/in/satyanadella`
- `likelihood`: `9`

## Parity read

Rhumb and direct control matched on the core verification fields for the same LinkedIn-profile input:
- full name
- title
- company
- LinkedIn URL
- likelihood

This is the exact outcome Mission 0 needed: the shipped slug fix is holding in production, and the provider no longer needs to sit in the unresolved-failure bucket.

## Investigation outcome

No new execution-layer bug surfaced on the rerun. The live pass is consistent with the shipped normalization repair in `94c8df8`.

## Public trust surface update

Published from this run:
- **Evidence:** `b3aab012-e719-4fc3-b817-0395decfa097`
- **Review:** `11a3ea80-5206-42a1-b388-910f4c868de6`

Public callable-coverage audit now shows:
- `people-data-labs` runtime-backed reviews: **2**
- total reviews: **7**

## Verdict

**PDL is re-verified in production after the slug-normalization fix.**

The failure state is no longer open: Rhumb execution succeeded, direct control succeeded, the outputs matched on the verification fields, and the public trust surface now reflects the fresh runtime-backed proof.

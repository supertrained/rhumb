# Runtime review loop — PDL fix-verify investigation + Algolia weakest-bucket pass

Date: 2026-03-29
Owner: Pedro / Keel runtime review loop

## Mission 0 — PDL fix-verify rerun exposed a new execution bug

### What failed first

Mission 0 started with the required PDL production rerun after the earlier slug-normalization repair in commit `94c8df8`.

The first fresh rerun did **not** complete cleanly.

Observed behavior:
- direct PDL control succeeded against `GET /v5/person/enrich`
- the Rhumb execute call returned `200`, but `provider_used` came back as **`apollo`**, not `people-data-labs`
- that meant the Phase 3 path was incomplete and had to move into investigation mode instead of just logging a pass

## Investigation

### Root cause

The failure was **not** a new PDL slug-alias break.

The real issue was in the execute request parser:
- `POST /v1/capabilities/{id}/execute` parsed only the JSON envelope fields
- query-string envelope fields like `provider` and `credential_mode` were ignored on POST
- a raw provider-native JSON payload (for example `{ "profile": "..." }`) was not automatically wrapped under `body`

That combination silently degraded into:
- `provider = None`
- `credential_mode = auto`
- provider auto-selection for `data.enrich_person`
- Apollo being chosen instead of PDL

So the exact bug was:
**execute request parsing could silently drop the intended provider/body shape and reroute the call to the wrong managed provider.**

### Why this mattered

This was a real execution-layer defect, not operator noise:
- the request looked natural because `execute/estimate` already accepts query params
- the live route did not fail loudly
- it silently auto-routed to a different provider
- that is precisely the kind of Phase 3 mismatch Mission 0 is supposed to catch

## Fix shipped

Committed + pushed:
- `9fd0872` — **Fix execute envelope parsing and expand maps coverage**

Execution-layer fix inside that commit:
- `packages/api/routes/capability_execute.py`
  - query-string envelope fields now populate missing POST execute envelope fields
  - raw provider-native JSON bodies are wrapped into `body` when the execute envelope is omitted
- `packages/api/tests/test_capability_execute.py`
  - added regression coverage for the exact failing pattern:
    - query-string envelope (`provider`, `credential_mode`, `method`, `path`)
    - top-level raw provider payload as JSON body

Validation:
- `pytest packages/api/tests/test_capability_execute.py -q`
- passed

## Cleanup before re-verification

Because the first malformed rerun published incorrect public trust rows, I removed the bad artifacts before re-running:
- deleted the wrong PDL review/evidence pair
- deleted the wrong Algolia review/evidence pair from the same malformed pass

That restored the public trust surface to the pre-run truth before publishing corrected evidence.

## Production re-verification after the fix

After push + deploy, I reran Mission 0 using the **same shorthand execute shape that had failed**:
- `POST /v1/capabilities/data.enrich_person/execute?provider=people-data-labs&credential_mode=rhumb_managed`
- body:
  ```json
  {
    "profile": "https://www.linkedin.com/in/satyanadella/"
  }
  ```

### PDL results after deploy

#### Rhumb Resolve
- provider used: **`people-data-labs`**
- credential mode: **`rhumb_managed`**
- upstream status: **200**
- matched fields:
  - `full_name`: `satya nadella`
  - `job_title`: `board member`
  - `job_company_name`: `starbucks`
  - `linkedin_url`: `linkedin.com/in/satyanadella`

#### Direct PDL control
- status: **200**
- returned the same values for the same fields

### Mission 0 verdict

Mission 0 now completed correctly:
- failure reproduced
- root cause identified
- fix shipped
- tests passed
- pushed to production
- live rerun confirmed the fix works in production

### Public trust surface update

Published fresh corrected proof:
- Evidence: `3d73776a-4ef4-428b-ae8e-811781290e4e`
- Review: `8e7d4e8e-2322-4ffe-999d-1e3252636955`

Depth moved:
- `people-data-labs` runtime-backed reviews: **6 → 7**

## Mission 1 — weakest-bucket callable provider pass

### Provider selection

Fresh pre-loop audit after cleanup showed the weakest callable bucket was back to **7 providers at 2 runtime-backed reviews**:
- `algolia`
- `apify`
- `apollo`
- `e2b`
- `exa`
- `replicate`
- `unstructured`

I chose **Algolia** because it has the cleanest deterministic parity path:
- explicit managed path template with `indexName`
- safe internal index `rhumb_test`
- exact top-hit comparison against direct control

### Test setup

#### Rhumb Resolve
- Estimate: `GET /v1/capabilities/search.autocomplete/execute/estimate?provider=algolia&credential_mode=rhumb_managed`
- Execute: `POST /v1/capabilities/search.autocomplete/execute?provider=algolia&credential_mode=rhumb_managed`
- Request body:
  ```json
  {
    "indexName": "rhumb_test",
    "query": "rhumb"
  }
  ```
- Request shape intentionally used the same fixed shorthand pattern as Mission 0

#### Direct provider control
- Endpoint: `POST https://80LYFTF37Y-dsn.algolia.net/1/indexes/rhumb_test/query`
- Body:
  ```json
  {
    "query": "rhumb"
  }
  ```

### Results

#### Rhumb Resolve
- provider used: **`algolia`**
- upstream status: **200**
- `nbHits`: **1**
- top hit:
  - `objectID`: `1`
  - `name`: `Rhumb Runtime Test`

#### Direct Algolia control
- status: **200**
- `nbHits`: **1**
- top hit:
  - `objectID`: `1`
  - `name`: `Rhumb Runtime Test`

### Verdict

Algolia passed with exact parity on the corrected production execute path.

### Public trust surface update

Published fresh proof:
- Evidence: `af5ee1a9-fb9f-4c44-b6a7-31ad889c94d6`
- Review: `d4088857-d7aa-4a97-980b-6b7a42e04444`

Depth moved:
- `algolia` runtime-backed reviews: **2 → 3**

## Coverage impact

Pre-loop after cleanup:
- weakest callable depth: **2 reviews across 7 providers**

Post-loop:
- weakest callable depth: **2 reviews across 6 providers**

Remaining weakest bucket:
- `apify`
- `apollo`
- `e2b`
- `exa`
- `replicate`
- `unstructured`

## Mission 2 — discovery expansion

After verification work, I expanded the **maps** category.

Why maps:
- live category depth was only **5** providers
- maps/geocoding/place lookup remain common agent tasks
- existing depth was too thin for routing, geocoding, local search, and field-ops demand

Added services:
- `tomtom-maps`
- `locationiq`
- `opencage`
- `maptiler`
- `loqate`

Discovery artifacts:
- `packages/api/migrations/0117_maps_expansion.sql`
- `docs/runbooks/discovery-expansion/2026-03-29-maps-expansion.md`

Strongest Phase 0 wedge:
- `maps.geocode_forward`
- `maps.geocode_reverse`
- `places.search_text`

Best first provider target:
- **TomTom Maps**

## Artifact bundle

- `artifacts/callable-review-coverage-2026-03-29-pre-loop-20260329T151300Z.json`
- `artifacts/runtime-review-pass-20260329T151300Z-pdl-algolia-fix-verified.json`
- `artifacts/proxy-services-2026-03-29-20260329T151300Z.json`
- `artifacts/callable-review-coverage-2026-03-29-post-loop-20260329T151300Z.json`

## Final verdict

This run completed all three missions in order:
1. **PDL failure was investigated to root cause, fixed in product code, pushed, and re-verified live**
2. **Algolia received the next weakest-bucket runtime-backed review with direct-provider parity**
3. **Maps discovery depth expanded by five services with a clear Phase 0 wedge**

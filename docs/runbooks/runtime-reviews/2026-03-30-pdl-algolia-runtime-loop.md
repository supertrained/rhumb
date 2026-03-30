# 2026-03-30 — PDL reconfirm + Algolia investigation / rerun

## Goal
Close the top Mission 0 / Mission 1 runtime-verification loop honestly:
- rerun **PDL** immediately after the earlier slug-normalization ship (`94c8df8`)
- take the next weakest callable provider by freshness ordering
- if anything fails, investigate the root cause instead of logging and moving on

At the start of this pass:
- weakest callable runtime-backed depth was **3** across **7** providers
- `algolia` was the oldest remaining provider in that weakest bucket
- `people-data-labs` had already been fixed previously, but the cron explicitly required a fresh production reconfirm

## What happened

### 1) PDL reconfirm passed on production
A temp review agent was created in production and granted only `people-data-labs` + `algolia` for the parity check bundle.

Artifact:
- `artifacts/runtime-review-pass-20260330T070511Z-pdl-algolia-current.json`

PDL parity result:
- estimate: **200**
- Rhumb-managed execute: **200**
- direct PDL control: **200**
- compared fields matched:
  - `full_name`
  - `job_title`
  - `job_company_name`
  - `linkedin_url`

Verdict:
- the earlier PDL slug-normalization fix remains good in current production
- no regression was found on the shorthand execute path

### 2) First Algolia pass failed — investigation required
The first Algolia managed call returned upstream **400** while direct control succeeded.

Initial artifact:
- `artifacts/runtime-review-pass-20260330T070511Z-pdl-algolia-current.json`

Observed mismatch:
- direct control targeted explicit index `rhumb_test`
- managed execute body only sent `query: "rhumb"`
- live managed config still uses templated path:
  - `POST /1/indexes/{indexName}/query`

Direct trace of the execution path showed:
- capability: `search.autocomplete`
- provider: `algolia`
- live managed config row present for `service_slug = algolia`
- API domain resolved correctly to `80LYFTF37Y-dsn.algolia.net`
- auth injection was correct:
  - `X-Algolia-API-Key`
  - `X-Algolia-Application-Id`
- the actual failure was input/path templating, not slug or auth wiring

### Root cause
This was **not** a slug-normalization or credential-injection bug.

The managed request and direct control request were not equivalent:
- direct control used an explicit `indexName` (`rhumb_test`)
- managed execution omitted `indexName`
- Algolia requires an index-specific path, so the initial pass was an invalid runtime-review input bundle

That made the first failure a **review-harness parity bug / missing input guard**, not an Algolia provider outage and not a broken Rhumb auth path.

### 3) Fix applied locally
To prevent this class of opaque failure from recurring, product code was updated locally to:
- normalize common Algolia aliases:
  - `index` → `indexName`
  - `index_name` → `indexName`
- fail early with a clear **400** when a managed path template input is missing instead of silently stripping the placeholder and returning an opaque upstream 400

Files changed:
- `packages/api/services/rhumb_managed.py`
- `packages/api/tests/test_rhumb_managed.py`

New coverage added:
- Algolia alias mapping / path-parameter stripping test
- clear error on missing managed path-template param test

Validation:
- `pytest packages/api/tests/test_rhumb_managed.py -q`
- passed

### 4) Algolia rerun with equivalent inputs passed
After correcting the parity inputs, the production rerun used the same explicit index on both sides:

Managed / direct input:
```json
{
  "indexName": "rhumb_test",
  "query": "rhumb"
}
```

Rerun artifacts:
- `artifacts/runtime-review-pass-20260330T070738Z-algolia-current-rerun.json`
- `artifacts/runtime-review-publication-20260330T070738Z-algolia-rerun.json`

Rerun result:
- estimate: **200**
- Rhumb-managed execute: **200**
- direct Algolia control: **200**
- parity matched on:
  - `nbHits`
  - top `objectID`
  - top `name`

Publication rows inserted:
- evidence: `60353cba-d960-49ca-b4ba-f591f1d39e8b`
- review: `487d620c-5d3a-4684-aae8-c71ed59cbbcc`

## Public audit result
Post-publication callable audit:
- artifact: `artifacts/callable-review-coverage-2026-03-30-post-algolia-rerun.json`
- `algolia` depth moved **3 → 4**
- weakest callable runtime-backed depth remains **3**
- weakest bucket shrank **7 → 6**

Remaining weakest-bucket providers:
- `apify`
- `apollo`
- `e2b`
- `exa`
- `replicate`
- `unstructured`

## Outcome
Mission 0 completed honestly:
- PDL was rerun in production and passed
- the first Algolia failure was investigated rather than logged away
- root cause was traced to missing managed path input parity, not auth or slug wiring
- a local guard + alias fix was added
- Algolia was rerun in production with equivalent inputs and passed
- public trust depth advanced **3 → 4**

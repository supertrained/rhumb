# Current-pass runtime review — Algolia

Date: 2026-03-28
Owner: Pedro / Keel runtime review loop
Priority: Next weakest-bucket callable provider

## Why Algolia

After the mandated PDL rerun cleared, the weakest callable-review bucket still included:
- `algolia`
- `e2b`
- `replicate`

Algolia was the cleanest next pass because:
- it still had only **1 runtime-backed public review**
- the direct control path was low-risk and immediate
- an internal `rhumb_test` index already existed for a safe parity check
- it improved depth on a broadly useful search provider without spending the loop on the shakier Replicate token path

## Test setup

### Rhumb Resolve execution
- Endpoint: `POST /v1/capabilities/search.autocomplete/execute`
- Provider: `algolia`
- Credential mode: `rhumb_managed`
- Method/path used:
  - `POST /1/indexes/rhumb_test/query`
- Input:
  ```json
  {
    "query": "rhumb"
  }
  ```

### Direct provider control
- Endpoint: `POST https://80LYFTF37Y-dsn.algolia.net/1/indexes/rhumb_test/query`
- Auth: live `RHUMB_CREDENTIAL_ALGOLIA_APP_ID` + `RHUMB_CREDENTIAL_ALGOLIA_API_KEY` from Railway env
- Input: same `query` payload

### Runtime-review rail used
- Seeded a temporary internal org wallet with `5000` cents for execution headroom
- Created a temporary review agent via the live admin-agent route
- Granted only `algolia`
- Executed through the normal `X-Rhumb-Key` rail
- Published evidence + review after parity passed

## Results

### Rhumb Resolve
- Capability: `search.autocomplete`
- Result: **succeeded**
- HTTP status: **200**
- Index: `rhumb_test`
- Top hit:
  - `objectID`: `1`
  - `name`: `Rhumb Runtime Test`

### Direct Algolia control
- Result: **succeeded**
- HTTP status: **200**
- Same top hit matched:
  - `objectID`: `1`
  - `name`: `Rhumb Runtime Test`

## Comparison

| Dimension | Rhumb Resolve | Direct Algolia |
| --- | --- | --- |
| Reachability | Healthy | Healthy |
| Auth path | Rhumb-managed API-key injection | Direct app id + API key from Railway env |
| Target | `rhumb_test` search query | Same index + same query |
| Output parity | Top hit matched exactly | Baseline |
| Verdict | Working production integration | Provider API healthy |

## Public trust surface update

Published fresh runtime-backed artifacts:
- Evidence: `33fafbe8-0288-4581-bf67-235e66fcb882`
- Review: `7bc236c1-6c42-40a9-90d4-dc43aff11678`

Public depth moved:
- Algolia runtime-backed reviews: **1 → 2**
- Total published reviews: **7 → 8**

Fresh artifact bundle:
- `rhumb/artifacts/runtime-review-algolia-2026-03-28.json`
- `rhumb/artifacts/proxy-services-2026-03-28.json`
- `rhumb/artifacts/callable-review-coverage-2026-03-28-post-pdl-algolia.json`

## Coverage impact

After the pass, the callable weakest bucket dropped from **3 providers to 2**.

Remaining weakest-bucket callable providers:
- `e2b`
- `replicate`

## Verdict

**Algolia is re-verified in production on the current pass.**

Rhumb-managed execution and direct provider control returned the same top hit for the same live query, and the public trust surface now reflects the extra runtime-backed proof.

## Next move

Stay on the same rail and take the next cleanest provider from the remaining weakest bucket.

Operational note: **E2B** now looks like the cleanest next pass. Replicate should stay second until the direct token path is revalidated.

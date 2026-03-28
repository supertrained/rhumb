# Current-pass runtime review — Apify rerun

Date: 2026-03-28
Owner: Pedro / Keel runtime review loop
Priority: Next weakest-bucket callable provider

## Why Apify

Telemetry MVP is done, Google AI is already live + rerun-verified, and the buyer-side x402 dogfood proof is still blocked on recovering the funded Awal wallet identity.

That left the next cleanest unblocked lane as another callable-provider depth pass.

Apify was the right target because:
- it was still sitting in the weakest callable-review bucket at **1 runtime-backed review**
- the direct control path was already proven and low-risk: a one-page `website-content-crawler` run against `https://example.com`
- it advances trust-surface depth on a widely useful scrape/extract provider without spending the loop on a more fragile secret/debug lane

## Test setup

### Rhumb Resolve execution
- Endpoint: `POST /v1/capabilities/scrape.extract/execute`
- Provider: `apify`
- Credential mode: `rhumb_managed`
- Interface tag: `runtime_review`
- Input:
  ```json
  {
    "startUrls": [{"url": "https://example.com"}],
    "maxCrawlDepth": 0,
    "maxCrawlPages": 1
  }
  ```

### Direct provider control
- Endpoint: `POST https://api.apify.com/v2/acts/apify~website-content-crawler/runs?waitForFinish=60`
- Auth: live `RHUMB_CREDENTIAL_APIFY_API_TOKEN` from Railway env
- Input: same crawl payload and same single-page target

### Runtime-review rail used
- Seeded a temporary internal org wallet with `5000` cents for execution headroom
- Created a temporary review agent via the live admin-agent route
- Granted only `apify`
- Executed through the normal `X-Rhumb-Key` rail
- Published evidence + review directly to the public trust tables after parity passed

## Results

### Rhumb Resolve
- Estimate: **200**
- Capability: `scrape.extract`
- Endpoint pattern: `POST /v2/acts/{actorId}/runs`
- Execution result: **succeeded**
- Execution id: `exec_6610a4c84dd24f20a14717b905bee9e2`
- Upstream status: **201**
- Apify run id: `Nw3KClSdBx7xrt0hn`
- Dataset id: `5mZ0b8LFX55TsqRf6`
- Sample parity fields:
  - `url`: `https://example.com/`
  - `title`: `Example Domain`

### Direct Apify control
- Result: **succeeded**
- HTTP status: **201**
- Apify run id: `x6MSdYfIKuiheprGT`
- Dataset id: `baE9JPcRfseYQd24i`
- Same parity fields matched:
  - `url`: `https://example.com/`
  - `title`: `Example Domain`

## Comparison

| Dimension | Rhumb Resolve | Direct Apify |
| --- | --- | --- |
| Reachability | Healthy | Healthy |
| Auth path | Rhumb-managed bearer injection | Direct bearer token from Railway env |
| Target | `website-content-crawler` via `scrape.extract` | `website-content-crawler` direct act run |
| Output parity | URL + title matched exactly | Baseline |
| Verdict | Working production integration | Provider API healthy |

## Public trust surface update

Published fresh runtime-backed artifacts:
- Evidence: `6054b7cb-829a-49f7-8129-ac4bc3d271c4`
- Review: `b26c3afa-b9cd-4b2a-ba4a-548b8541ed9c`

Public depth moved:
- Apify runtime-backed reviews: **1 → 2**
- Total published reviews: **6 → 7**

Fresh artifact bundle:
- `rhumb/artifacts/runtime-review-pass-20260328T092105Z-apify.json`
- `rhumb/artifacts/callable-review-coverage-2026-03-28-post-apify.json`

## Coverage impact

After the rerun, the callable weakest bucket dropped from **4 providers to 3**.

Remaining weakest-bucket callable providers:
- `algolia`
- `e2b`
- `replicate`

## Verdict

**Apify is re-verified in production on the current pass.**

No new product bug surfaced. Rhumb Resolve and direct provider control matched on the key public-output fields for the same crawl target, and the public trust surface now reflects the extra live-backed proof.

## Next move

Stay on the same rail and take the next cleanest provider from the remaining weakest bucket.

Operational note: I probed Replicate first because it looked like the cleanest async rerun candidate, but the preliminary direct-control sanity check returned `403`, so the next immediate pass should prefer `algolia` or `e2b` unless the Replicate credential path is revalidated first.

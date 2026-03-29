# Current-pass runtime review — Apify rerun

Date: 2026-03-29
Owner: Pedro / Keel runtime review loop
Priority: Next weakest-bucket callable provider

## Why Apify

Telemetry MVP is done, Google AI wiring is already live, and the buyer-side wallet-prefund dogfood proof is still honestly blocked on funded exportable buyer-wallet access.

That left the next cleanest unblocked lane as another callable-provider depth pass.

Apify was the right target because:
- it was still sitting in the weakest callable-review bucket at **2 runtime-backed reviews**
- the direct control path was already proven and low-risk: a one-page `website-content-crawler` run against `https://example.com`
- it advances trust-surface depth on a broadly useful scrape/extract provider without spending the loop on a more fragile secret/debug lane

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
- Pulled the first item from both Apify datasets and compared public output fields
- Published evidence + review directly to the public trust tables after parity passed

## Results

### Rhumb Resolve
- Estimate: **200**
- Capability: `scrape.extract`
- Endpoint pattern: `POST /v2/acts/{actorId}/runs`
- Execution result: **succeeded**
- Execution id: `exec_6568e7af098d4e76ac29fca7371fe25f`
- Upstream status: **201**
- Apify run id: `fZI1NBGhae5sJXucR`
- Dataset id: `Hx2d11LnyzlsWeLXn`
- Sample parity fields:
  - `url`: `https://example.com/`
  - `metadata.title`: `Example Domain`
  - `markdown`: matched direct control exactly

### Direct Apify control
- Result: **succeeded**
- HTTP status: **201**
- Apify run id: `bRxkKaAGXcnLTUKLJ`
- Dataset id: `nWdwcdFk34j7v0Yqn`
- Same parity fields matched:
  - `url`: `https://example.com/`
  - `metadata.title`: `Example Domain`
  - `markdown`: exact match

## Comparison

| Dimension | Rhumb Resolve | Direct Apify |
| --- | --- | --- |
| Reachability | Healthy | Healthy |
| Auth path | Rhumb-managed bearer injection | Direct bearer token from Railway env |
| Target | `website-content-crawler` via `scrape.extract` | `website-content-crawler` direct act run |
| Output parity | URL + metadata.title + markdown matched exactly | Baseline |
| Verdict | Working production integration | Provider API healthy |

## Public trust surface update

Published fresh runtime-backed artifacts:
- Evidence: `962598f0-8639-4047-80d7-8b473c271362`
- Review: `b49abfe9-b42e-41da-bc1d-b77894d4c364`

Fresh artifact bundle:
- `rhumb/artifacts/runtime-review-pass-20260329T201922Z-apify-current-pass.json`
- `rhumb/artifacts/callable-review-coverage-2026-03-29-pre-apify-current-pass.json`
- `rhumb/artifacts/callable-review-coverage-2026-03-29-post-apify-current-pass.json`

## Coverage impact

After the rerun, the callable weakest bucket dropped from **3 providers to 2**.

Remaining weakest-bucket callable providers:
- `e2b`
- `replicate`

Apify public depth moved:
- runtime-backed reviews: **2 → 3**
- total published reviews: **7 → 8**

## Verdict

**Apify is re-verified in production on the current pass.**

No new product bug surfaced. Rhumb Resolve and direct provider control matched on the key public-output fields for the same crawl target, and the public trust surface now reflects the extra live-backed proof.

## Next move

Stay on the same rail and take the next cleanest provider from the remaining weakest bucket.

Operational note: the strongest current next target is `e2b`; `replicate` remains viable but is still more likely to burn time on provider-side credit or throttle friction.

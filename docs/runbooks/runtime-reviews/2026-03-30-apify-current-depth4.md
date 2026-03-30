# Apify current-depth publication — depth 3 → 4

Date: 2026-03-30
Owner: Pedro / Keel runtime review loop
Status: passed

## Why Apify

Telemetry is already shipped. The wallet-prefund dogfood lane remains honestly blocked on funded exportable buyer-wallet access, and Google AI wiring is already live. That left callable-review depth expansion as the highest-leverage unblocked product lane.

A fresh public callable audit before this pass showed the weakest bucket at depth **3** across:
- `apify`
- `e2b`
- `replicate`

Apify was the correct next target because it was the **stalest** provider in that weakest bucket and it has a low-friction direct control path for exact parity.

## Runtime-review rail used

Used the normal temp-agent production review rail:
- seeded a temporary org with `5000` cents of execution headroom
- created a temporary review agent
- granted only `apify`
- executed through the normal `X-Rhumb-Key` rail
- compared Rhumb-managed execution against direct Apify control
- published a fresh runtime-backed evidence + review pair after parity passed
- disabled the temporary review agent after publication

Review agent:
- agent id: `bd0a3e97-1de2-4a2c-8382-220a6690c85e`

## Test setup

### Rhumb-managed path
- Estimate: `GET /v1/capabilities/scrape.extract/execute/estimate?provider=apify&credential_mode=rhumb_managed`
- Execute: `POST /v1/capabilities/scrape.extract/execute`
- Payload:
  ```json
  {
    "startUrls": [{"url": "https://example.com"}],
    "maxCrawlDepth": 0,
    "maxCrawlPages": 1
  }
  ```

### Direct provider control
- Execute: `POST https://api.apify.com/v2/acts/apify~website-content-crawler/runs?waitForFinish=60`
- Dataset fetch: `GET https://api.apify.com/v2/datasets/{datasetId}/items?clean=true&limit=1`
- Auth: live `RHUMB_CREDENTIAL_APIFY_API_TOKEN` from Railway production env
- Same payload and same one-page target as the Rhumb-managed path

## Results

### Rhumb-managed execution
- estimate: **200**
- execution id: `exec_5577ccd1a80d48caa01894ded94fa646`
- upstream status: **201**
- run id: `IfCSlfgpUp9HH2jeV`
- dataset id: `APQWL4z4MaWLBHeAU`
- sample parity fields:
  - `url`: `https://example.com/`
  - `metadata.title`: `Example Domain`
  - `markdown`: exact match

### Direct Apify control
- status: **201**
- run id: `hYs5IzGZSIksARea3`
- dataset id: `Bfw3zlM6doxNmBDB3`
- sample parity fields:
  - `url`: `https://example.com/`
  - `metadata.title`: `Example Domain`
  - `markdown`: exact match

## Comparison

| Dimension | Rhumb-managed | Direct Apify | Result |
|---|---|---|---|
| Reachability | 200 wrapper / 201 upstream | 201 | Match |
| Target | `website-content-crawler` via `scrape.extract` | same direct actor | Match |
| Sample URL | `https://example.com/` | `https://example.com/` | Match |
| Sample title | `Example Domain` | `Example Domain` | Match |
| Sample markdown | exact | exact | Match |
| Verdict | working production integration | provider API healthy | Match |

## Public trust surface update

Published fresh runtime-backed rows:
- evidence: `09485d09-d57d-4f00-a75b-bf0a52396c18`
- review: `09c2000b-aa2e-400a-9101-804b010281e0`

Artifacts:
- `rhumb/artifacts/runtime-review-pass-20260330T123041Z-apify-current-depth4.json`
- `rhumb/artifacts/runtime-review-publication-2026-03-30-apify-depth4.json`
- `rhumb/artifacts/callable-review-coverage-2026-03-30-pre-next-pass.json`
- `rhumb/artifacts/callable-review-coverage-2026-03-30-post-apify-depth4.json`

Reusable operator helper added:
- `rhumb/scripts/runtime_review_apify_depth4_20260330.py`

## Coverage impact

Fresh public callable audit after publication:
- `apify` moved **3 → 4** runtime-backed reviews
- `apify` is now **4 / 9** on the public trust surface
- weakest callable runtime-backed depth remains **3**
- weakest bucket shrank from **3 providers → 2**
- remaining weakest providers:
  - `e2b`
  - `replicate`

## Verdict

**Apify is re-verified in production on the current-depth rail.**

No new product bug surfaced. Rhumb-managed `scrape.extract` matched direct Apify control on the same one-page crawl target, the public trust surface now reflects the extra live-backed proof, and the honest next weakest-bucket candidates are now `e2b` and `replicate`.

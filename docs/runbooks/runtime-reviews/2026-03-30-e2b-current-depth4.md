# Current-depth runtime review — E2B depth 4 publication

Date: 2026-03-30
Owner: Pedro OODA build loop
Priority: next clean weakest-bucket callable provider after Apify

## Why E2B

This pass first re-checked the honest top blocker: whether a funded operator-controlled Base EOA with an exportable private key was available right now for `rhumb/scripts/wallet_prefund_dogfood.py`.

It still was not:
- no `RHUMB_DOGFOOD_WALLET_PRIVATE_KEY` surfaced in the active env
- no funded exportable buyer wallet surfaced in current working notes

That kept wallet-prefund dogfood externally blocked, so the correct unblocked move was to keep shrinking the weakest callable-review bucket.

Fresh pre-pass audit confirmed:
- weakest runtime-backed callable depth: **3**
- weakest bucket size: **2**
- weakest providers: `e2b`, `replicate`
- by freshness ordering, **E2B** was the cleanest next weakest-bucket provider

## Test setup

### Rhumb Resolve execution
- Estimate: `GET /v1/capabilities/agent.spawn/execute/estimate?provider=e2b&credential_mode=rhumb_managed`
- Create sandbox: `POST /v1/capabilities/agent.spawn/execute`
- Status check: `POST /v1/capabilities/agent.get_status/execute`
- Template:
  - alias: `base`
  - timeout: `300`
  - metadata:
    - `source=rhumb-runtime-review`
    - `service=e2b`
    - `stamp=20260330T143343Z`

### Direct provider control
- Create sandbox: `POST https://api.e2b.app/sandboxes`
- Status check: `GET https://api.e2b.app/sandboxes/{sandboxID}`
- Same template alias, timeout, and metadata as the Rhumb-managed path

### Runtime-review rail used
- temp org: `org_runtime_review_e2b_20260330t143343z_de4cd479`
- seeded balance: `5000` cents
- temp review agent: `27888391-6182-45e6-bed2-20134cc2775e`
- service grant: `e2b` only
- temp access row: `b79bf4eb-3471-4bd5-a3d7-fe829b280573`
- execution rail: normal `X-Rhumb-Key` path
- cleanup: both created sandboxes deleted after verification; temp review agent disabled after publish

## Results

### Rhumb Resolve
- Estimate: **200 OK**
- Endpoint pattern: `POST /sandboxes`
- Create wrapper: **200 OK**
- Create upstream: **201 Created**
- Create execution id: `exec_99c8cb89972f4aa790a9e6f9d407bef5`
- Created sandbox id: `ilsqmoee9eht0t6l2ybkz`
- Resolved template alias: `base`
- Resolved template id: `rki5dems9wqfm4r03t7g`
- envd version: `0.5.8`
- Status wrapper: **200 OK**
- Status upstream: **200 OK**
- Status execution id: `exec_afeef348445d454792025090a1a388e5`
- Sandbox state: `running`
- CPU / memory: `2` / `512 MB`

### Direct E2B control
- Create: **201 Created**
- Created sandbox id: `inuvz5u87lhdx0jd12rc4`
- Resolved template alias: `base`
- Resolved template id: `rki5dems9wqfm4r03t7g`
- envd version: `0.5.8`
- Status: **200 OK**
- Sandbox state: `running`
- CPU / memory: `2` / `512 MB`

### Comparison

Parity checks passed on:
- exact template alias equality
- exact internal template id equality
- exact runtime state equality (`running`)
- exact `envdVersion` equality (`0.5.8`)
- exact compute-shape equality (`cpuCount=2`, `memoryMB=512`)

Verdict: **production parity passed cleanly**.

### Cleanup
- Rhumb-created sandbox delete: **204**
- direct-control sandbox delete: **204**
- temp review agent disabled: **true**

## Public trust surface update

Published fresh runtime-backed rows:
- evidence: `05d945bd-df23-41aa-969e-42a7e91c07f7`
- review: `b1ea4fd5-28ce-47a8-ad44-e42615146342`

Artifacts:
- `rhumb/artifacts/runtime-review-pass-20260330T143343Z-e2b-current-depth4.json`
- `rhumb/artifacts/runtime-review-publication-2026-03-30-e2b-depth4.json`
- `rhumb/artifacts/callable-review-coverage-2026-03-30-pre-e2b-depth4.json`
- `rhumb/artifacts/callable-review-coverage-2026-03-30-post-e2b-depth4.json`

Reusable helper added:
- `rhumb/scripts/runtime_review_e2b_depth4_20260330.py`

## Coverage impact

Post-publish audit confirmed:
- E2B runtime-backed review depth: **3 → 4**
- total published E2B reviews: **8 → 9**
- weakest callable-review bucket size: **2 → 1**
- weakest runtime-backed callable depth stays **3**, but now only across:
  - `replicate`

## Verdict

**E2B is now pushed above the weakest callable-review bucket.**

The honest blocker order remains:
1. funded exportable buyer-wallet proof for wallet-prefund dogfood is still externally blocked
2. Google AI wiring does **not** need reopening
3. the next best unblocked lane is another callable depth-expansion pass, with **Replicate** now the sole remaining weakest-bucket provider

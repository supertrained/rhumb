# E2B — current-pass runtime review

Date: 2026-03-28
Operator: Pedro / Keel runtime loop
Status: passed

## Why E2B

Telemetry MVP is already done, dogfood is still blocked on recovering the funded Awal buyer wallet identity, and Google AI is already live plus rerun-verified. That left the callable weakest bucket as the cleanest unblocked lane.

Before this pass, the public callable coverage audit showed:
- `e2b`: **1 runtime-backed review / 6 total**
- `replicate`: **1 runtime-backed review / 6 total**

E2B had the cleaner direct-control surface, so it was the right next move.

## Runtime-review rail used

I reused the cleaner production review rail:
- seeded a temporary internal org wallet with review headroom
- created a temporary review agent via the live admin-agent route
- granted only `e2b`
- executed via normal `X-Rhumb-Key`
- compared Rhumb-managed execution against direct E2B control
- deleted both created sandboxes after verification

Review agent:
- agent id: `a1c7d8a1-1c96-4ae6-87d8-953e5f4ef525`

Artifacts from the live run:
- runtime artifact: `rhumb/artifacts/runtime-review-e2b-2026-03-28.json`
- callable audit refresh: `rhumb/artifacts/callable-review-coverage-2026-03-28-post-e2b.json`

## Test setup

### Rhumb-managed path
- Estimate: `GET /v1/capabilities/agent.spawn/execute/estimate?provider=e2b&credential_mode=rhumb_managed`
- Create sandbox: `POST /v1/capabilities/agent.spawn/execute`
- Status check: `POST /v1/capabilities/agent.get_status/execute`
- Payload:
  - template alias: `base`
  - timeout: `300`
  - metadata: `source=rhumb-runtime-review`, `service=e2b`

### Direct provider control
- Create sandbox: `POST https://api.e2b.app/sandboxes`
- Status check: `GET https://api.e2b.app/sandboxes/{sandboxID}`
- Same payload and metadata as the Rhumb-managed path

## Results

### Rhumb-managed execution
- estimate: **200**
- create execution id: `exec_aef9ea83d0894048aade60f0756ae100`
- create upstream status: **201**
- created sandbox id: `ihjzh6axiumy1jvj1mtmg`
- resolved template alias: `base`
- resolved template id: `rki5dems9wqfm4r03t7g`
- status execution id: `exec_98f18add98a044b8897c5122c4eba247`
- status upstream status: **200**
- sandbox state: `running`
- envd version: `0.5.4`
- CPU / memory: `2` / `512 MB`

### Direct E2B control
- create status: **201**
- created sandbox id: `iz3zzpyaiyr3p1dxwi6wm`
- resolved template alias: `base`
- resolved template id: `rki5dems9wqfm4r03t7g`
- status: **200**
- sandbox state: `running`
- envd version: `0.5.4`
- CPU / memory: `2` / `512 MB`

### Cleanup
- Rhumb-created sandbox delete: **204**
- direct-control sandbox delete: **204**

## Comparison

| Dimension | Rhumb-managed | Direct E2B | Result |
|---|---|---|---|
| Create reachability | 200 wrapper / 201 upstream | 201 | Match |
| Template resolution | alias `base`, id `rki5dems9wqfm4r03t7g` | alias `base`, id `rki5dems9wqfm4r03t7g` | Match |
| Status reachability | 200 | 200 | Match |
| Runtime state | `running` | `running` | Match |
| Sandbox shape | envd `0.5.4`, CPU `2`, memory `512` | envd `0.5.4`, CPU `2`, memory `512` | Match |
| Cleanup | deleted | deleted | Match |

## Public trust surface update

After the live pass:
- inserted runtime-backed evidence `dae883bd-b674-4310-ae5c-0cc75977833b`
- published review `8d71c878-98e2-40a2-ad6a-94788392a7d9`
- linked the review to the evidence in `review_evidence_links`

## Coverage impact

Post-pass callable audit:
- `e2b` moved **1 → 2** runtime-backed reviews
- `e2b` is now **2 / 7** on the public review surface
- the callable weakest bucket shrank from **2 providers → 1 provider**
- the remaining weakest callable provider is now **`replicate`**

## Operator note

The only comparison gotcha was that E2B returns an internal `templateID` plus a human alias (`base`). The right parity check is **internal template id equality + alias equality**, not `templateID == "base"`.

## Verdict

**E2B is now current-pass rerun verified in production.**

Rhumb-managed `agent.spawn` + `agent.get_status` matched direct E2B control on template resolution, running state, sandbox shape, and cleanup behavior, and the public trust surface now reflects the second runtime-backed review.

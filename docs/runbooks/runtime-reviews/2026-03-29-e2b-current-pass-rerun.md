# E2B — current-pass rerun

Date: 2026-03-29
Operator: Pedro / Keel runtime loop
Status: passed

## Why E2B

Telemetry MVP is already done, Google AI wiring is already live plus rerun-verified, and the wallet-prefund dogfood lane is still honestly blocked on a funded exportable buyer EOA. That left callable-review depth as the cleanest unblocked lane.

Before this pass, the public callable coverage audit showed:
- `e2b`: **2 runtime-backed reviews / 7 total**
- `replicate`: **2 runtime-backed reviews / 7 total**

E2B remained the cleaner direct-control target, so it was the right move before spending more time on Replicate credit / throttle risk.

## Runtime-review rail used

Used the standard temp-agent production rail:
- seeded a temporary internal org wallet with review headroom
- created a temporary review agent via the live admin-agent route
- granted only `e2b`
- executed through the normal `X-Rhumb-Key` rail
- compared Rhumb-managed execution against direct E2B control
- deleted both created sandboxes after verification
- disabled the temporary review agent after publish

Review agent:
- agent id: `83b523be-c645-4248-a502-fbaf1618e382`

Artifacts from the live run:
- runtime artifact: `rhumb/artifacts/runtime-review-e2b-2026-03-29-current-pass.json`
- callable audit refresh: `rhumb/artifacts/callable-review-coverage-2026-03-29-post-e2b-current-pass.json`

## Test setup

### Rhumb-managed path
- Estimate: `GET /v1/capabilities/agent.spawn/execute/estimate?provider=e2b&credential_mode=rhumb_managed`
- Create sandbox: `POST /v1/capabilities/agent.spawn/execute`
- Status check: `POST /v1/capabilities/agent.get_status/execute`
- Payload:
  - template alias: `base`
  - timeout: `300`
  - metadata: `source=rhumb-runtime-review`, `service=e2b`, `stamp=20260329T222435Z`

### Direct provider control
- Create sandbox: `POST https://api.e2b.app/sandboxes`
- Status check: `GET https://api.e2b.app/sandboxes/{sandboxID}`
- Same payload and metadata as the Rhumb-managed path

## Results

### Rhumb-managed execution
- estimate: **200**
- create execution id: `exec_ec3b062b69b544a5b73ad3e0ec1bc45c`
- create upstream status: **201**
- created sandbox id: `iyodtwbpxn19d0fj425i4`
- resolved template alias: `base`
- resolved template id: `rki5dems9wqfm4r03t7g`
- status execution id: `exec_66f189a3ff054210a2e5a7f3351b2269`
- status upstream status: **200**
- sandbox state: `running`
- envd version: `0.5.4`
- CPU / memory: `2` / `512 MB`

### Direct E2B control
- create status: **201**
- created sandbox id: `iduuepibn8vk9d6m84f5j`
- resolved template alias: `base`
- resolved template id: `rki5dems9wqfm4r03t7g`
- status: **200**
- sandbox state: `running`
- envd version: `0.5.4`
- CPU / memory: `2` / `512 MB`

### Cleanup
- Rhumb-created sandbox delete: **204**
- direct-control sandbox delete: **204**
- review agent disabled: **true**

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
- inserted runtime-backed evidence `1891ea72-44cb-40cc-8f60-f69872cd3e67`
- published review `c8fe777d-c98a-477e-9073-38196aaaaec0`
- linked the review to the evidence in `review_evidence_links`

## Coverage impact

Post-pass callable audit:
- `e2b` moved **2 → 3** runtime-backed reviews
- `e2b` is now **3 / 8** on the public review surface
- the callable weakest bucket shrank from **2 providers → 1 provider**
- the remaining weakest callable provider is now **`replicate`**

## Operator note

The same comparison rule still applies: E2B returns both a human alias (`base`) and an internal template id. The parity check should compare **alias equality + internal template id equality**, not `templateID == "base"`.

## Verdict

**E2B is now current-pass rerun verified again in production.**

Rhumb-managed `agent.spawn` + `agent.get_status` matched direct E2B control on template resolution, running state, sandbox shape, and cleanup behavior, and the public callable weakest bucket is now down to a single provider: `replicate`.

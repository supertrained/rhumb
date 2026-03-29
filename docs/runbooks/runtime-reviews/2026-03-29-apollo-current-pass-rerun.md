# Current-pass runtime review — Apollo rerun

Date: 2026-03-29
Owner: Pedro / Keel runtime loop
Priority: Next weakest-bucket callable provider after Google AI was already confirmed live and dogfood remained blocked on a funded operator EOA
Status: passed in production

## Why Apollo

This cron pass started from the honest priority stack:
- telemetry MVP is already done
- wallet-prefund dogfood is still blocked on a funded operator-controlled EOA
- Google AI config wiring is already live and rerun-verified in production

That made the next unblocked lane another callable-review depth pass.

A fresh callable audit at the top of the pass showed the weakest runtime-backed bucket at **2 reviews across 6 providers**:
- `apify`
- `apollo`
- `e2b`
- `exa`
- `replicate`
- `unstructured`

Apollo was the cleanest next target because it is:
- read-only
- deterministic enough for same-input parity
- cheap to rerun
- already proven on the managed rail, so this pass could focus on fresh public trust depth

## Runtime-review rail used

- Seeded a temporary internal org wallet with `5000` cents for execution headroom
- Created a temporary review agent via the live admin-agent route
- Granted only `apollo`
- Executed through the standard `X-Rhumb-Key` rail
- Published evidence + review directly to the public trust spine after parity passed

Review agent:
- agent id: `9f773bdc-1dcd-4471-8e7c-f763c5d1f160`
- organization id: `org_runtime_review_apollo_20260329162114`

Artifacts from this live run:
- runtime artifact: `artifacts/runtime-review-pass-20260329T162114Z-apollo-current-pass.json`
- callable audit refresh: `artifacts/callable-review-coverage-2026-03-29-post-apollo-current.json`

## Test setup

### Rhumb-managed path
- Estimate: `GET /v1/capabilities/data.enrich_person/execute/estimate?provider=apollo&credential_mode=rhumb_managed`
- Execute: `POST /v1/capabilities/data.enrich_person/execute?provider=apollo&credential_mode=rhumb_managed`
- Request body:
  ```json
  {
    "email": "tim@apple.com"
  }
  ```
- Request shape intentionally used the fixed shorthand execute style:
  - query-string envelope for `provider` + `credential_mode`
  - raw provider-native JSON body

### Direct provider control
- Endpoint: `POST https://api.apollo.io/api/v1/people/match`
- Auth: live Apollo API key from Railway env
- Header note: used `curl` with a normal browser-like user agent to avoid control-client edge-policy noise
- Request body:
  ```json
  {
    "email": "tim@apple.com"
  }
  ```

## Results

### Rhumb-managed execution
- estimate: **200**
- execute wrapper status: **200**
- upstream status: **200**
- execution id: `exec_7bc508dee4fa4a66a53d4fa5be2e178e`
- provider used: **`apollo`**
- credential mode: **`rhumb_managed`**
- org credits remaining: **4996 cents**

Matched verification fields:
- `name`: `Yenni Tim`
- `title`: `Founder and Director, UNSW PRAxIS (Practice x Implementation Science) Lab`
- `organization_name`: `null`
- `linkedin_url`: `http://www.linkedin.com/in/yennitim`
- `email_status`: `null`

### Direct Apollo control
- HTTP status: **200**

Matched verification fields:
- `name`: `Yenni Tim`
- `title`: `Founder and Director, UNSW PRAxIS (Practice x Implementation Science) Lab`
- `organization_name`: `null`
- `linkedin_url`: `http://www.linkedin.com/in/yennitim`
- `email_status`: `null`

## Comparison

| Dimension | Rhumb-managed | Direct Apollo | Result |
| --- | --- | --- | --- |
| Reachability | Healthy | Healthy | Match |
| Routing | `provider_used=apollo` | Direct Apollo control | Match |
| Auth path | Rhumb-managed credential injection | Direct Apollo key | Match |
| Request shape | Fixed shorthand execute path | Provider-native body | Expected |
| Output parity | Name/title/org/linkedin/email status matched | Baseline | Match |

## Operator note

`tim@apple.com` still resolves to Apollo’s same unexpected underlying record (`Yenni Tim`). That is not a new Rhumb bug. The point of this pass was parity, and parity was exact on the chosen verification fields.

## Public trust surface update

Published from this run:
- Evidence: `1a7b528c-2b02-416d-aafe-982245c117bc`
- Review: `51934a40-7b40-49cb-af32-f4f93a052e8a`

## Coverage impact

Post-publication callable audit showed:
- `apollo` runtime-backed reviews: **2 → 3**
- weakest callable runtime-backed depth remains **2**, but the bucket shrank **6 providers → 5**

Remaining weakest-bucket callable providers:
- `apify`
- `e2b`
- `exa`
- `replicate`
- `unstructured`

## Verdict

**Apollo is current-pass rerun verified in production.**

The managed execution lane, the fixed shorthand execute path, and direct provider control all agreed on the live parity fields, and the public trust surface now reflects the additional runtime-backed proof.

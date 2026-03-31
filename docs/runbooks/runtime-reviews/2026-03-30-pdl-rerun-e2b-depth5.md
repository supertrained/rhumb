# Runtime review loop — PDL fix-verify rerun + E2B depth-5 publication

Date: 2026-03-30
Owner: Pedro / Keel runtime review loop
Priority: Mission 0 fix-verify first, then weakest callable provider by runtime-backed review depth

## Mission 0 — PDL fix-verify rerun

The run started by explicitly re-checking **People Data Labs** after the slug-normalization fix shipped in commit `94c8df8`.

### Why this rerun mattered

A previously-fixed Phase 3 issue does not count as resolved until the canonical production path is exercised again. The goal here was to verify that the old slug-normalization failure still does **not** recur on the live `people-data-labs` path.

### Execution path exercised

- Capability: `data.enrich_person`
- Provider requested: `people-data-labs`
- Credential mode: `rhumb_managed`
- Input: `https://www.linkedin.com/in/satyanadella/`
- Estimate path: `GET /v1/capabilities/data.enrich_person/execute/estimate`
- Execute path: `POST /v1/capabilities/data.enrich_person/execute`
- Direct control: `GET https://api.peopledatalabs.com/v5/person/enrich`

### Result

- Estimate: **200**
- Rhumb-managed wrapper: **200**
- `provider_used`: **`people-data-labs`**
- Rhumb upstream status: **402**
- Direct provider control: **402**
- Execution id: `exec_6c1e679658dd4314ab7a38e2623fcf3b`
- Artifact: `artifacts/runtime-review-pass-20260331T030536Z-pdl-unstructured-depth4.json`

### Interpretation

This rerun did what Mission 0 required:
- the canonical slug still resolves correctly through Rhumb
- the old normalization bug did **not** recur
- both Rhumb and direct control now stop at the same provider quota boundary (`account maximum / all matches used`)

That means this pass did **not** surface a new execution-layer bug inside Rhumb. No slug-alias, auth-injection, credential-store, or execution-config repair was required for PDL in this run.

Because the direct control lane immediately hit the same provider quota wall, this remained an internal verification artifact only rather than a new published trust row.

## Mission 1 — E2B current-depth runtime rerun

Fresh pre-pass callable audit:
- callable providers: **16**
- weakest runtime-backed callable depth: **4**
- weakest bucket: `e2b`, `replicate`
- artifact: `artifacts/callable-review-coverage-2026-03-30-pre-e2b-depth5.json`

Within that bucket, **E2B** was the stalest provider by freshest public runtime evidence timestamp, so it became the next honest target.

## Runtime-review rail used

- temp org: `org_runtime_review_e2b_20260331t031005z_44e19d19`
- seeded balance: `5000` cents
- temp review agent: `f3430ca0-edad-48b9-a95e-8f04aec2435f`
- service grant: `e2b` only
- temp access row: `7fb3fadc-c22d-4c74-b89e-ee2cfd60cef0`
- execution rail: normal `X-Rhumb-Key` path via Railway production context
- cleanup: both Rhumb-created and direct-control sandboxes deleted cleanly; temp review agent disabled after publish

## Managed execution

- Capabilities: `agent.spawn` + `agent.get_status`
- Provider: `e2b`
- Credential mode: `rhumb_managed`
- Estimate: **200 OK**
- Create wrapper: **200 OK**
- Status wrapper: **200 OK**
- Create execution id: `exec_798581fbdacb48379892553c3e2e397a`
- Status execution id: `exec_58fb342171234fcbb88054f9fcfce653`
- Rhumb sandbox id: `ikbnc7dvwp3petebl58mr`
- Upstream create/status: **201 / 200**

Rhumb-managed E2B output matched on:
- template alias: `base`
- template id: `rki5dems9wqfm4r03t7g`
- sandbox state: `running`
- `envdVersion`: `0.5.8`
- compute shape: `cpuCount=2`, `memoryMB=512`

## Direct provider control

- Endpoint: `POST https://api.e2b.app/sandboxes`
- Status endpoint: `GET https://api.e2b.app/sandboxes/{sandboxId}`
- Auth: Railway production `RHUMB_CREDENTIAL_E2B_API_KEY`
- Same template payload and metadata as the Rhumb-managed path
- Direct create/status: **201 / 200**
- Direct sandbox id: `it7zea6gxcecasj83kwoi`

Direct control produced the same operational values:
- template alias: `base`
- template id: `rki5dems9wqfm4r03t7g`
- sandbox state: `running`
- `envdVersion`: `0.5.8`
- compute shape: `cpuCount=2`, `memoryMB=512`

Cleanup also matched cleanly:
- Rhumb-created sandbox delete: **204**
- direct-control sandbox delete: **204**

## Parity verdict

Managed and direct executions matched exactly on:
- template alias
- internal template id
- running state
- envd version
- sandbox compute shape

Verdict: **production parity passed cleanly**.

## Public trust surface update

Published fresh runtime-backed rows:
- evidence: `1bac562e-4b78-4aae-ac2b-f8a9db1b0a78`
- review: `0e2720b4-bd62-492a-ad71-5ea38224f262`

Artifacts:
- `artifacts/runtime-review-pass-20260331T031005Z-e2b-current-depth5.json`
- `artifacts/runtime-review-publication-2026-03-30-e2b-depth5.json`
- `artifacts/callable-review-coverage-2026-03-30-pre-e2b-depth5.json`
- `artifacts/callable-review-coverage-2026-03-30-post-e2b-depth5.json`
- `scripts/runtime_review_e2b_depth5_20260330.py`

## Coverage impact

Post-publish audit confirmed:
- E2B runtime-backed review depth: **4 → 5**
- total published E2B reviews: **9 → 10**
- weakest callable-review bucket size: **2 → 1**
- weakest runtime-backed callable depth stays **4**, now only across:
  - `replicate`

That makes **`replicate`** the next freshness-ordered callable-review target.

## Verdict

- **PDL fix-verify remains clean on the canonical production path.**
- **E2B is freshly re-verified in production at depth 5.**
- No new Rhumb execution-layer repair was required in this run because no managed/direct divergence appeared.

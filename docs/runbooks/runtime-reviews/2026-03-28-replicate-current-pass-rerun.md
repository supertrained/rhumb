# Runtime review — Replicate current pass rerun

Date: 2026-03-28
Owner: Pedro
Mission: Mission 1 — callable weakest-bucket runtime verification

## Why Replicate

After the earlier PDL reconfirm and the latest callable-review coverage refresh, **Replicate** was the weakest callable provider by runtime-backed review depth.

It had only **1 runtime-backed public review** before this pass.

## Test setup

### Rhumb Resolve execution
- Endpoint: `POST /v1/capabilities/ai.generate_text/execute`
- Provider: `replicate`
- Credential mode: `rhumb_managed`
- Input:
  ```json
  {
    "version": "5a6809ca6288247d06daf6365557e5e429063f32a21146b2a807c682652136b8",
    "input": {
      "prompt": "Reply with exactly REPLICATE_RUNTIME_OK",
      "system_prompt": "You are a precise assistant.",
      "max_new_tokens": 20,
      "temperature": 0.1
    }
  }
  ```

### Direct provider control
- Endpoint: `POST https://api.replicate.com/v1/predictions`
- Same version and input shape
- Direct poll: `GET /v1/predictions/{id}`

### Runtime-review rail used
- Seeded a temporary internal org wallet with `5000` cents for execution headroom
- Created a temporary review agent via the live admin-agent route
- Granted `replicate`
- Executed through the normal `X-Rhumb-Key` rail

## Results

### Rhumb Resolve
- Execute HTTP status: **200**
- Upstream status: **201**
- Execution ID: `exec_fd8f4589a4cf4f36af83e60395640830`
- Prediction ID: `p5wmw8whtdrnc0cx6kzs0esms4`
- Final provider status after poll: **succeeded**
- Output text: `REPLICATE_RUNTIME_OK`

### Direct provider control
- First create attempt: **429**
- Provider message: low-credit create-prediction throttle with `retry_after=10`
- Retry after reset: **201**
- Retry prediction ID: `c28hhy8q35rnc0cx6m09dg1gxr`
- Final provider status after poll: **succeeded**
- Output text: `REPLICATE_DIRECT_OK`

## Comparison

| Dimension | Rhumb Resolve | Direct provider control |
| --- | --- | --- |
| Reachability | Healthy | Healthy after throttle reset |
| Auth path | Rhumb-managed token injection | Direct Replicate token |
| Execute behavior | Prediction create + async completion | Prediction create + async completion |
| Final status | succeeded | succeeded |
| Verdict | Working production integration | Provider healthy |

## Investigation outcome

The first direct-control request returned a **provider-side 429**, not a Rhumb error.

That matters because Mission 0 requires investigation instead of shallow logging:
- Rhumb did **not** fail this pass
- the control failure was due to Replicate's low-credit create-prediction throttle
- waiting for the reset window and retrying the control call produced a clean provider-side success
- that means there was **no Rhumb execution-layer bug** to fix here

So the correct conclusion is not "Replicate failed". The correct conclusion is:
- Rhumb lane: healthy
- provider lane: healthy
- transient control throttle: real, but upstream-side and recoverable

## Public trust surface update

Published fresh runtime-backed artifacts:
- Evidence: `87c1a62b-d6c1-4ebd-ab27-64dbeb9d7b1c`
- Review: `9ea73714-deee-4fdf-9982-e96bcc2a7696`

Coverage impact:
- Replicate runtime-backed reviews: **1 → 2**
- Replicate total published reviews: **6 → 7**
- Weakest callable-review bucket is now **2 runtime-backed reviews** instead of a single trailing provider

Fresh artifact bundle:
- `rhumb/artifacts/runtime-review-replicate-2026-03-28.json`
- `rhumb/artifacts/callable-review-coverage-2026-03-28-post-replicate.json`

## Verdict

**Replicate passes a fresh production runtime verification through both Rhumb Resolve and direct provider control.**

The only failure observed in this pass was an initial direct-provider throttle, and that was resolved by retrying after the provider's reset window. No Rhumb-side fix was required.

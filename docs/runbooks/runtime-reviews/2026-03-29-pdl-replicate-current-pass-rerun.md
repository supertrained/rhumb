# Current-pass runtime review — PDL reconfirm + Replicate rerun

Date: 2026-03-29
Owner: Pedro / Keel runtime review loop
Status: completed

Artifacts:
- `rhumb/artifacts/runtime-review-pass-20260329T231345Z-pdl-replicate-current.json`
- `rhumb/artifacts/callable-review-coverage-2026-03-29-pre-replicate-current-pass.json`
- `rhumb/artifacts/callable-review-coverage-2026-03-29-post-replicate-current-pass-unpublished.json`

## Why this pass

Mission 0 explicitly required a fresh production rerun for **PDL** after the slug-normalization fix that landed in commit `94c8df8`.

Fresh callable coverage at the start of the pass showed:
- callable providers live: **16**
- weakest runtime-backed depth: **2**
- lone weakest callable provider: **`replicate`**

So the honest sequence for this run was:
1. rerun **PDL** first to confirm the fix still works in production
2. take **Replicate** as the current weakest-bucket callable provider
3. compare Rhumb-managed execution against direct provider control on both

## Operational note — first attempt was incomplete

The first PDL retry using the shared Atlas API key returned **`insufficient_credits` / `no_org_credits`** before reaching PDL.

That was **not** a PDL regression and **not** a valid Mission 0 completion.

To finish the mission honestly, the pass switched to the standard temp-review-agent rail:
- inserted a temporary org in Supabase
- seeded `5000` cents into `org_credits`
- created temporary review agent `06b352f9-05f7-4064-9432-c9c8de858276`
- granted only `people-data-labs` and `replicate`
- reran both providers through the normal `X-Rhumb-Key` execution path
- disabled the review agent after verification

Temp review org:
- `org_runtime_review_20260329t231345z`

## Mission 0 — PDL reconfirm after slug-normalization fix

### Rhumb-managed path
- Capability: `data.enrich_person`
- Provider: `people-data-labs`
- Credential mode: `rhumb_managed`
- Estimate: **200**
- Execution: **200**
- Execution id: `exec_ef1ebbd65dfc4e20bcdd1633dbafc120`
- Upstream status: **200**
- Provider used: `people-data-labs`

### Direct control path
- Endpoint: `GET https://api.peopledatalabs.com/v5/person/enrich`
- Input: `profile=https://www.linkedin.com/in/satyanadella/`
- Direct status: **200**

### Parity check

| Field | Rhumb-managed | Direct PDL | Result |
|---|---|---|---|
| `full_name` | `satya nadella` | `satya nadella` | Match |
| `job_title` | `board member` | `board member` | Match |
| `job_company_name` | `starbucks` | `starbucks` | Match |
| `linkedin_url` | `linkedin.com/in/satyanadella` | `linkedin.com/in/satyanadella` | Match |

### Mission 0 verdict

**PDL passes again in production on the fixed shorthand execute path.**

The canonical slug `people-data-labs` now resolves cleanly through Rhumb-managed execution and matches direct PDL control on the key public fields.

No additional execution-layer bug surfaced on this rerun.

## Mission 1 — Replicate weakest-bucket rerun

### Rhumb Resolve execution
- Capability: `ai.generate_text`
- Provider: `replicate`
- Credential mode: `rhumb_managed`
- Estimate: **200**
- Execution wrapper: **200**
- Execution id: `exec_c512c7fc9e4c4d35a5f2a675eb71e97c`
- Upstream create status: **201**
- Prediction id: `nmdsfz0qz1rnc0cx7fg9g0cerw`
- Final status after provider poll: **`succeeded`**
- Final output: `REPLICATE_CURRENT_PASS_OK_20260329T231345Z`

### Direct Replicate control
- Endpoint: `POST https://api.replicate.com/v1/predictions`
- Same model version and same prompt
- Create status: **201**
- Prediction id: `txxtxyt269rnc0cx7fgbk0rc5g`
- Final status after poll: **`succeeded`**
- Final output: `REPLICATE_CURRENT_PASS_OK_20260329T231345Z`

### Comparison

| Dimension | Rhumb Resolve | Direct Replicate | Result |
|---|---|---|---|
| Estimate reachability | 200 | n/a | Healthy |
| Create reachability | 200 wrapper / 201 upstream | 201 | Match |
| Final provider status | `succeeded` | `succeeded` | Match |
| Final output | `REPLICATE_CURRENT_PASS_OK_20260329T231345Z` | `REPLICATE_CURRENT_PASS_OK_20260329T231345Z` | Match |

### Mission 1 verdict

**Replicate is re-verified on the current pass.**

Rhumb-managed execution and direct Replicate control matched on create success, terminal state, and exact final text output for the same prompt.

No execution-layer bug surfaced in this pass.

## Coverage note

A fresh callable audit was rerun after the pass.

Because this run only logged the verification artifact and did **not** publish a new public evidence/review row, the public callable coverage table is unchanged:
- weakest runtime-backed depth remains **2**
- remaining weakest callable provider on the public trust surface remains **`replicate`**

That is a trust-surface bookkeeping gap, not a runtime execution failure.

## Verdict

This run completed the required fix-verify loop honestly:
- **PDL** was rerun after the shipped normalization fix and passed against direct control
- **Replicate** was rerun as the weakest callable provider and passed against direct control
- the initial PDL `insufficient_credits` result was investigated instead of hand-waved away
- the fix was operational, not code-level: switch from the underfunded shared agent to the proper temp-review-agent rail with seeded review credits

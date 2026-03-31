# 2026-03-31 — PDL fix-verify rerun + Replicate current-depth publication

## Goal
Execute the mandated Mission 0 fix-verify rerun for **People Data Labs** after the earlier slug-normalization repair, then take the current weakest callable provider to the next runtime-backed review depth.

At the start of this pass:
- `GET /v1/proxy/services` still showed **16 callable providers**
- fresh callable coverage audit showed weakest runtime-backed callable depth **4**
- the sole weakest-bucket provider was **`replicate`**
- Mission 0 still explicitly required a fresh canonical-slug PDL rerun instead of relying on earlier same-day history

Artifacts created up front:
- `artifacts/callable-review-coverage-2026-03-31-pre-replicate-depth5.json`
- `artifacts/proxy-services-2026-03-31-current.json`

## Mission 0 — PDL rerun

### Why it still mattered
PDL had previously suffered from a canonical-slug execution bug. The fix had already shipped, but the cron instruction for this pass was explicit: rerun the live canonical path again now and treat a stale note as insufficient.

### What was executed
Used the linked Railway production context and the existing temp review-agent rail to run:
- `GET /v1/capabilities/data.enrich_person/execute/estimate?provider=people-data-labs&credential_mode=rhumb_managed`
- `POST /v1/capabilities/data.enrich_person/execute?provider=people-data-labs&credential_mode=rhumb_managed`
- direct control: `GET https://api.peopledatalabs.com/v5/person/enrich`

Input:
- `profile=https://www.linkedin.com/in/satyanadella/`

Artifact:
- `artifacts/runtime-review-pass-20260331T071419Z-pdl-unstructured-depth4.json`

### Observed result
- estimate: **200**
- Rhumb execute wrapper: **200**
- `provider_used`: **`people-data-labs`**
- Rhumb upstream status: **402**
- direct provider control: **402**
- execution id: `exec_d4fadbc24b3c419abb1330888e558eab`

### Investigation verdict
This rerun did **not** reproduce the old slug-normalization failure.

What it proved instead:
- the canonical provider path still resolves through Rhumb correctly
- Rhumb is still reaching **People Data Labs**, not a stale alias or wrong upstream
- both Rhumb and direct control now stop at the exact same provider-side quota boundary: `account maximum for person enrichment (all matches used)`

That means there was **no new Rhumb execution-layer bug** to fix in this run. The old slug issue stayed fixed; the current limiter is provider quota, not routing, auth injection, or credential lookup.

## Mission 1 — Replicate current-depth pass

### Why Replicate
Fresh public callable audit before the pass showed:
- weakest runtime-backed callable depth: **4**
- sole weakest-bucket provider: **`replicate`**

### Runtime-review rail used
Used the live temp-agent production rail:
- temp org: `org_runtime_review_replicate_20260331t071553z_2a6704bd`
- temp review agent: `02127113-e229-433f-906a-340b4d05e105`
- granted only `replicate`
- executed through normal `X-Rhumb-Key`
- compared against direct Replicate control using the same pinned model version
- disabled the temp review agent after publish

### Test setup
#### Rhumb-managed path
- estimate: `GET /v1/capabilities/ai.generate_text/execute/estimate?provider=replicate&credential_mode=rhumb_managed`
- execute: `POST /v1/capabilities/ai.generate_text/execute?provider=replicate&credential_mode=rhumb_managed`
- pinned version: `5a6809ca6288247d06daf6365557e5e429063f32a21146b2a807c682652136b8`
- prompt: `Reply with exactly REPLICATE_CURRENT_DEPTH5_OK_20260331T071553Z`

#### Direct provider control
- create: `POST https://api.replicate.com/v1/predictions`
- poll: `GET https://api.replicate.com/v1/predictions/{id}`
- same pinned version and identical input payload

### Results
#### Rhumb-managed
- wrapper status: **200**
- upstream create status: **201**
- execution id: `exec_5805e0cb4c5a4f3ba88d97b086156168`
- prediction id: `3bddx7p7w5rnc0cx8azvvcp89c`
- final provider status: **succeeded**
- final output: `REPLICATE_CURRENT_DEPTH5_OK_20260331T071553Z`

#### Direct provider control
- create status: **201**
- prediction id: `ye3phzqr4drne0cx8azr0jgndm`
- final provider status: **succeeded**
- final output: `REPLICATE_CURRENT_DEPTH5_OK_20260331T071553Z`
- note: direct create hit temporary **429 throttling** twice before succeeding on the third attempt after honoring `retry_after`

### Comparison
Managed and direct paths matched on:
- final status
- exact output string
- pinned model-version behavior

Artifact:
- `artifacts/runtime-review-pass-20260331T071553Z-replicate-current-depth5.json`

### Public trust-surface publication
Published the new Replicate runtime-backed evidence/review pair.

Publication artifact:
- `artifacts/runtime-review-publication-2026-03-31-replicate-depth5.json`

Inserted rows:
- evidence: `ddc04041-4d4c-4676-9f33-5baf7853432e`
- review: `846d18ec-88d1-4bbb-a3bf-1a8791853400`

### Coverage impact
Fresh post-publication audit confirmed:
- artifact: `artifacts/callable-review-coverage-2026-03-31-post-replicate-depth5.json`
- `replicate` moved **4 -> 5** runtime-backed reviews
- weakest callable runtime-backed depth moved **4 -> 5**
- the new weakest bucket now includes:
  - `algolia`
  - `apify`
  - `apollo`
  - `brave-search-api`
  - `e2b`
  - `exa`
  - `firecrawl`
  - `google-ai`
  - `replicate`
  - `tavily`
  - `unstructured`

## Outcome
- Mission 0: **PDL rerun completed**; canonical slug path still works and the only observed failure is provider-side quota, not a Rhumb regression.
- Mission 1: **Replicate depth-5 pass completed**; Rhumb-managed and direct provider control matched exactly on terminal status and exact output text.
- Public callable-review floor is now **depth 5**, not depth 4.

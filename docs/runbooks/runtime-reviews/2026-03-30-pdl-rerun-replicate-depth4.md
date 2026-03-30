# 2026-03-30 — PDL rerun + Replicate current-depth publication

## Goal
Execute the mandated Mission 0 fix-verify rerun for **People Data Labs** after the earlier slug-normalization repair, then take the current weakest callable provider to the next runtime-backed review depth.

At the start of this pass:
- `GET /v1/proxy/services` still showed **16 callable providers**
- fresh callable coverage audit showed weakest runtime-backed callable depth **3**
- the sole weakest-bucket provider was **`replicate`**
- Mission 0 still explicitly required a fresh PDL rerun instead of relying on earlier same-day history

## Mission 0 — PDL rerun

### Why it still mattered
PDL had previously suffered from a canonical-slug execution bug. The repair shipped earlier, but the cron instruction for this pass was explicit: rerun it again now and do not stop at stale evidence.

### What was executed
Used the existing temp review-agent rail through the linked Railway production context:
- seeded a temp org with `5000` cents
- created a temporary review agent
- granted canonical `people-data-labs`
- ran:
  - `GET /v1/capabilities/data.enrich_person/execute/estimate?provider=people-data-labs&credential_mode=rhumb_managed`
  - `POST /v1/capabilities/data.enrich_person/execute?provider=people-data-labs&credential_mode=rhumb_managed`
- ran direct control against `GET https://api.peopledatalabs.com/v5/person/enrich`

Artifact:
- `artifacts/runtime-review-pass-20260330T150308Z-pdl-unstructured-depth4.json`

### Observed result
- estimate: **200**
- Rhumb execute wrapper: **200**
- provider used: **`people-data-labs`**
- Rhumb upstream status: **402**
- direct provider status: **402**
- both sides surfaced the same provider-side quota boundary: account maximum / all matches used

### Investigation outcome
This rerun did **not** reproduce the old slug-normalization failure.

What it proved instead:
- the canonical provider path is still reaching **People Data Labs**, not silently routing elsewhere
- Rhumb and direct provider control now fail in the same place for this input: provider quota
- there was **no new Rhumb execution-layer bug** to investigate or fix in this pass

So Mission 0 is satisfied as a fresh fix-verify rerun: the prior slug bug did not come back. The new limiting factor is provider quota, not Rhumb normalization.

## Mission 1 — Replicate current-depth pass

### Why Replicate
Fresh public callable audit before the pass:
- weakest runtime-backed callable depth: **3**
- sole weakest-bucket provider: **`replicate`**

Artifacts:
- `artifacts/callable-review-coverage-2026-03-30-pre-replicate-depth4.json`
- `artifacts/proxy-services-2026-03-30-current.json`

### Runtime-review rail used
Used the live temp-agent production rail:
- seeded temp org `org_runtime_review_replicate_20260330t150458z_6fa57e72`
- created temp review agent `16a5a70f-c858-4d5f-9db1-bf2f4708eaf5`
- granted only `replicate`
- executed through normal `X-Rhumb-Key`
- compared against direct Replicate control using the same pinned model version
- disabled the temp review agent after publish

### Test setup
#### Rhumb-managed path
- estimate: `GET /v1/capabilities/ai.generate_text/execute/estimate?provider=replicate&credential_mode=rhumb_managed`
- execute: `POST /v1/capabilities/ai.generate_text/execute?provider=replicate&credential_mode=rhumb_managed`
- pinned version: `5a6809ca6288247d06daf6365557e5e429063f32a21146b2a807c682652136b8`
- prompt: `Reply with exactly REPLICATE_CURRENT_DEPTH4_OK_20260330T150458Z`

#### Direct provider control
- create: `POST https://api.replicate.com/v1/predictions`
- poll: `GET https://api.replicate.com/v1/predictions/{id}`
- same version and identical input payload

### Results
#### Rhumb-managed
- wrapper status: **200**
- upstream create status: **201**
- execution id: `exec_c500390ae2d74550a11b03c65108ffb2`
- prediction id: `f9xesyz34xrnc0cx7x39s5jt1g`
- final provider status: **succeeded**
- final output: `REPLICATE_CURRENT_DEPTH4_OK_20260330T150458Z`

#### Direct provider control
- create status: **201**
- prediction id: `80t3g8geehrna0cx7x3tk07dam`
- final provider status: **succeeded**
- final output: `REPLICATE_CURRENT_DEPTH4_OK_20260330T150458Z`

### Comparison
Managed and direct paths matched on:
- final status
- exact output string
- pinned model-version behavior

Artifact:
- `artifacts/runtime-review-pass-20260330T150458Z-replicate-current-depth4.json`

## Public trust-surface publication
Published the new Replicate runtime-backed evidence/review pair.

Publication artifact:
- `artifacts/runtime-review-publication-2026-03-30-replicate-depth4.json`

Inserted rows:
- evidence: `1a31b019-dc5f-4785-b688-78d91623e540`
- review: `0e6ea787-4a2c-4b83-b346-a621455e8e2f`

Public spot-check artifact:
- `artifacts/replicate-reviews-spotcheck-2026-03-30.json`

## Coverage impact
Post-publication fresh audit:
- artifact: `artifacts/callable-review-coverage-2026-03-30-post-replicate-depth4.json`
- `replicate` moved **3 -> 4** runtime-backed reviews
- weakest callable runtime-backed depth moved **3 -> 4**
- there is no longer a depth-3 callable provider

Current depth-4 callable bucket now includes:
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

## Product helper shipped
Added reusable helper:
- `scripts/runtime_review_replicate_depth4_20260330.py`

## Outcome
- Mission 0: **PDL rerun completed**; canonical slug path still works and the only current failure is provider-side quota, not a Rhumb regression.
- Mission 1: **Replicate depth pass completed**; Rhumb-managed and direct provider control matched exactly on terminal status and exact output text.
- Public callable-review floor is now **depth 4**, not depth 3.

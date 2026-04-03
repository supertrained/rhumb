# Runtime review loop — PDL rerun + Replicate depth 10

Date: 2026-04-02
Owner: Pedro / Keel runtime review loop

## Mission 0 — PDL fix-verify rerun after slug-normalization fix `94c8df8`

### Why this rerun happened
This cron explicitly required a fresh production rerun for `people-data-labs` after the canonical slug-normalization fix in commit `94c8df8`, so I reran the live Phase 3 path first before touching any other provider.

### Rhumb execution
- Capability: `data.enrich_person`
- Provider: `people-data-labs`
- Credential mode: `rhumb_managed`
- Input: `profile=https://www.linkedin.com/in/satyanadella/`
- Estimate: **200**
- Execute: **200**
- Upstream provider status through Rhumb: **402**
- Provider used: **`people-data-labs`**
- Execution id: `exec_55d90f89d6d54ecd87c3c142cbd762ae`

### Direct control
- Endpoint: `GET https://api.peopledatalabs.com/v5/person/enrich`
- Status: **402**
- Direct provider message: `You have hit your account maximum for person enrichment (all matches used)`

### Comparison
- Rhumb and direct control hit the **same quota boundary**
- Error message parity matched exactly
- Canonical provider slug resolved correctly through the managed execution path
- No new execution-layer regression surfaced in this rerun

### Verdict
**PASS.** The `94c8df8` slug-normalization fix still holds live in production. The blocker remains provider quota, not Rhumb routing, auth injection, or execution config mapping.

### Artifact
- `artifacts/runtime-review-pass-20260403T034500Z-pdl-fix-verify-20260401b.json`

## Mission 1 — Replicate runtime review (depth 9 → 10)

### Why Replicate was selected
Fresh callable coverage from `GET /v1/proxy/services` + public review/evidence audit showed:
- callable providers: **16**
- weakest claim-safe runtime depth: **9**
- weakest bucket: `github`, `slack`, `stripe`, `replicate`, `algolia`, `twilio`

Within that weakest bucket, **Replicate** was the stalest provider by freshest public runtime evidence timestamp (`2026-03-31T07:16:12Z`), so it was the honest next freshness target after skipping already-rerun PDL.

### Rhumb execution
- Capability: `ai.generate_text`
- Provider: `replicate`
- Credential mode: `rhumb_managed`
- Estimate: **200**
- Execute: **200**
- Upstream provider status through Rhumb: **201**
- Provider used: **`replicate`**
- Execution id: `exec_6a218519bc0149008c896b05238b5bc2`
- Model version: `5a6809ca6288247d06daf6365557e5e429063f32a21146b2a807c682652136b8`
- Prompt: `Reply with exactly REPLICATE_DEPTH10_OK_20260403T034814Z`
- Final managed prediction id: `0xm6f1e805rnc0cxa5tb9mtns0`

### Direct provider control
- Endpoint: `POST https://api.replicate.com/v1/predictions`
- Final direct prediction id: `x0btq5qqt5rne0cxa5t8tqc2jw`
- Status: **201** create / **200** final poll
- Direct token source: live Railway production `RHUMB_CREDENTIAL_REPLICATE_API_TOKEN`
- Direct control hit two honest provider throttles first (`429`, retry-after `8s` then `2s`) before succeeding on the third create attempt; this was a provider-side low-credit create-rate limit, not a Rhumb execution-layer issue

### Comparison surface
Managed vs direct matched exactly on:
- final prediction status = `succeeded`
- exact text output = `REPLICATE_DEPTH10_OK_20260403T034814Z`
- same pinned model version and input payload shape

### Verdict
**PASS.** Rhumb Resolve preserved exact Replicate parity for this live generation check. No execution-layer investigation or fix was required.

### Published trust rows
- evidence: `ca5608c1-d9a0-4fe1-8986-d9042382b4b7`
- review: `9f009fa5-7ccc-4e74-862b-d5a86bc3d29d`

### Coverage impact
- Replicate claim-safe runtime-backed reviews: **9 → 10**
- Weakest callable depth stays **9**, but Replicate leaves the weakest bucket
- Post-pass weakest bucket: `github`, `slack`, `stripe`, `algolia`, `twilio`

### Artifacts
- `artifacts/runtime-review-pass-20260403T034814Z-replicate-depth10.json`
- `artifacts/runtime-review-publication-2026-04-02-replicate-depth10.json`
- `artifacts/callable-review-coverage-2026-04-02-pre-current-pass-from-cron-2045.json`
- `artifacts/callable-review-coverage-2026-04-02-post-replicate-current-pass-from-cron-2045.json`
- `scripts/runtime_review_replicate_depth10_20260402.py`

## Mission 2 — discovery expansion

### Category chosen
**Forms** remained underrepresented at **5 providers** despite being a common operational front door for:
- lead capture
- intake and onboarding workflows
- support escalation forms
- submissions that feed CRM, automation, or document pipelines

### Added services
- `formstack`
- `cognito-forms`
- `formsite`
- `zoho-forms`
- `wufoo`

### Phase 0 assessment
The cleanest first Resolve wedge is:
- `form.get`
- `form.responses.list`
- `form.response.get`

Best first provider target: **Formstack**.

### Discovery files
- `packages/api/migrations/0151_forms_expansion_ii.sql`
- `docs/runbooks/discovery-expansion/2026-04-02-forms-expansion-ii.md`

## Honest next runtime-review target
With Replicate lifted to depth 10, the freshness-ordered weakest callable target should now come from the remaining depth-9 bucket, starting with **Algolia** or **GitHub** after the next fresh coverage pull.

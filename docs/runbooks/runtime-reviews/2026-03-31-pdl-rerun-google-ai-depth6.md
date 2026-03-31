# Runtime review loop — PDL rerun + Google AI depth 6

Date: 2026-03-31
Owner: Pedro / Keel runtime review loop

## Why this pass

Mission 0 was fixed by directive: rerun canonical **People Data Labs** first after slug-normalization fix `94c8df8` and verify the canonical `people-data-labs` rail still works in production.

Mission 1 then had to take the callable provider with the fewest runtime-backed reviews. The pre-pass cache-busted audit showed **16 callable providers** with a weakest runtime-backed depth of **5** across 10 providers. Within that weakest bucket, **Google AI** was the stalest freshness candidate, so it became the next honest target.

## Mission 0 — PDL fix-verify rerun

### What was run
- Estimate:
  - `GET /v1/capabilities/data.enrich_person/execute/estimate?provider=people-data-labs&credential_mode=rhumb_managed`
- Managed execute:
  - `POST /v1/capabilities/data.enrich_person/execute?provider=people-data-labs&credential_mode=rhumb_managed`
- Direct control:
  - `GET https://api.peopledatalabs.com/v5/person/enrich`
- Input:
  - `profile=https://www.linkedin.com/in/satyanadella/`

### Result
- estimate: **200**
- Rhumb wrapper: **200**
- `provider_used`: **`people-data-labs`**
- Rhumb upstream: **402**
- direct provider control: **402**
- execution id: `exec_6bae275c47324bada8ca5033cc0f5be4`

### Conclusion
- canonical slug routing still works in production
- the old slug-normalization bug did **not** recur
- both lanes are now stopping at the same provider quota boundary (`account maximum / all matches used`)
- no new Rhumb execution-layer fix was required in this pass

Artifact:
- `artifacts/runtime-review-pass-20260331T152520Z-pdl-unstructured-depth4.json`

## Mission 1 — Google AI depth 5 → 6 freshness rerun

### Pre-pass coverage truth
Cache-busted audit before the pass:
- callable providers: **16**
- weakest runtime-backed depth: **5**
- weakest bucket size: **10**
- weakest bucket:
  - `algolia`
  - `apify`
  - `apollo`
  - `e2b`
  - `exa`
  - `firecrawl`
  - `google-ai`
  - `replicate`
  - `tavily`
  - `unstructured`
- Google AI was the stalest freshness candidate in that bucket.

### What was run
- Capability:
  - `ai.generate_text`
- Managed execute:
  - `POST /v1/capabilities/ai.generate_text/execute?provider=google-ai&credential_mode=rhumb_managed`
- Direct control:
  - `POST https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent`
- Prompt sentinel:
  - `RHUMB_GOOGLE_AI_20260331_DEPTH6`

### Result
Managed vs direct parity passed exactly on:
- HTTP status: **200 / 200**
- provider used: **`google-ai`**
- upstream status: **200**
- model version: **`gemini-2.5-flash`** on both lanes
- exact output text: **`RHUMB_GOOGLE_AI_20260331_DEPTH6`**

Published trust rows:
- evidence: `ebb6d939-b784-488f-baf1-21fd734d398e`
- review: `3c43ec0b-de6c-4ae0-9d91-009c5213d5e7`
- execution id: `exec_842761ebe36745d196b8daaabde3b78e`

### Post-pass coverage truth
Cache-busted audit after publication:
- `google-ai` moved **5 → 6** runtime-backed reviews
- weakest runtime-backed callable depth stayed **5**
- weakest bucket shrank **10 → 9**
- remaining weakest providers:
  - `algolia`
  - `apify`
  - `apollo`
  - `e2b`
  - `exa`
  - `firecrawl`
  - `replicate`
  - `tavily`
  - `unstructured`
- next freshness-ordered target is now **`tavily`**

## Structured runtime review verdict

### Rhumb execution
- succeeded
- preserved correct provider selection and auth injection
- returned the same model version and exact output text as direct control

### Direct provider control
- succeeded
- matched managed execution exactly on the observable output contract

### Comparison verdict
**Parity passed.** This is a clean runtime-backed review showing that Rhumb Resolve continues to execute Google AI correctly in production at current depth.

## Artifacts
- `artifacts/callable-review-coverage-2026-03-31-pre-current-pass.json`
- `artifacts/runtime-review-pass-20260331T152520Z-pdl-unstructured-depth4.json`
- `artifacts/runtime-review-pass-20260331T152821Z-google-ai-current-depth6.json`
- `artifacts/runtime-review-publication-2026-03-31-google-ai-depth6.json`
- `artifacts/callable-review-coverage-2026-03-31-post-google-ai-depth6.json`
- `scripts/runtime_review_google_ai_depth6_20260331.py`

## Verdict

PDL fix-verify remains clean: the slug fix holds and the current blocker is provider quota, not Rhumb routing.
Google AI is now lifted above the weakest depth bucket, and the callable-review freshness lane is ready to move to **Tavily** next.

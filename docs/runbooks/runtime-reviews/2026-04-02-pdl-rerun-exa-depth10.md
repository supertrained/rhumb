# Runtime review loop — PDL rerun + Exa depth 10

Date: 2026-04-02
Owner: Pedro / Keel runtime review loop

## Mission 0 — PDL fix-verify rerun after slug-normalization fix `94c8df8`

### Why this rerun happened
The fix-verify protocol explicitly requires a live Phase 3 rerun after a shipped execution-layer fix. `people-data-labs` had a canonical slug-normalization fix in commit `94c8df8`, so this pass reran the production path first before touching any other provider.

### Rhumb execution
- Capability: `data.enrich_person`
- Provider: `people-data-labs`
- Credential mode: `rhumb_managed`
- Input: `profile=https://www.linkedin.com/in/satyanadella/`
- Estimate: **200**
- Execute: **200**
- Upstream provider status through Rhumb: **402**
- Provider used: **`people-data-labs`**
- Execution id: `exec_93e922ff1c8044eba5b4125bfe8e137e`

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
**PASS.** The `94c8df8` slug-normalization fix still holds live in production. The current blocker is provider quota, not Rhumb routing, auth injection, or execution config mapping.

### Artifact
- `artifacts/runtime-review-pass-20260402T234606Z-pdl-fix-verify-20260401b.json`

## Mission 1 — Exa runtime review (depth 9 → 10)

### Why Exa was selected
Fresh callable coverage from `GET /v1/proxy/services` + public review/evidence audit showed:
- callable providers: **16**
- weakest claim-safe runtime depth: **9**
- weakest bucket: `github`, `slack`, `stripe`, `apify`, `exa`, `replicate`, `unstructured`, `algolia`, `twilio`

After skipping already-rerun PDL, **Exa** was the freshness-ordered next target in that weakest bucket.

### Rhumb execution
- Capability: `search.query`
- Provider: `exa`
- Credential mode: `rhumb_managed`
- Query: `best AI agent observability tools`
- numResults: `3`
- Estimate: **200**
- Execute: **200**
- Upstream provider status through Rhumb: **200**
- Provider used: **`exa`**
- Execution id: `exec_98651c27f3ac4a4a84acd915344f9f5f`

### Direct control
- Endpoint: `POST https://api.exa.ai/search`
- Status: **200**
- Same query and `numResults=3`

### Comparison surface
Managed vs direct matched exactly on:
- result count = `3`
- top result title
- top result URL
- ordered top-3 URL list

Matched top-3 URLs:
1. `https://www.braintrust.dev/articles/best-ai-agent-observability-tools-2026`
2. `https://www.reddit.com/r/AI_Agents/comments/1rfrvcw/whats_your_honest_tier_list_for_agent/`
3. `https://www.langchain.com/articles/llm-observability-tools`

### Verdict
**PASS.** Rhumb Resolve preserved exact Exa parity for this live search query. No execution-layer investigation or fix was required.

### Published trust rows
- evidence: `b31bf1e4-1495-4b86-943e-3d128a66faac`
- review: `7b7d11aa-b93d-4bf5-aadd-902272389d74`

### Coverage impact
- Exa claim-safe runtime-backed reviews: **9 → 10**
- Weakest callable depth stays **9**, but Exa leaves the weakest bucket
- Post-pass weakest bucket: `github`, `slack`, `stripe`, `apify`, `replicate`, `unstructured`, `algolia`, `twilio`

### Artifacts
- `artifacts/runtime-review-pass-20260402T234823Z-exa-depth10.json`
- `artifacts/runtime-review-publication-2026-04-02-exa-depth10.json`
- `artifacts/callable-review-coverage-2026-04-02-pre-exa-current-pass-from-cron-2346.json`
- `artifacts/callable-review-coverage-2026-04-02-post-exa-current-pass-from-cron-2348.json`

## Mission 2 — discovery expansion

### Category chosen
**Maps** remained underrepresented at **5 providers** despite high operational demand for:
- place search
- address normalization
- reverse geocoding
- routing and travel-time checks
- territory / proximity workflows

### Added services
- `tomtom`
- `geocodio`
- `openrouteservice`
- `traveltime`
- `positionstack`

### Phase 0 assessment
The cleanest first Resolve wedge is:
- `geocode.forward`
- `geocode.reverse`
- `place.search`

Best first provider target: **TomTom**.

### Discovery files
- `packages/api/migrations/0150_maps_expansion_ii.sql`
- `docs/runbooks/discovery-expansion/2026-04-02-maps-expansion-ii.md`

## Honest next runtime-review target
With Exa lifted to depth 10, the freshness-ordered weakest callable target should now come from the remaining depth-9 bucket, starting with **unstructured** or **apify** depending on the next fresh coverage pull.

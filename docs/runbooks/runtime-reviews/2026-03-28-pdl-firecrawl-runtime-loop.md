# 2026-03-28 Runtime Loop — PDL rerun + Firecrawl coverage lift

## Mission 0 — PDL rerun after slug-normalization fix

- **Provider:** `people-data-labs`
- **Capability:** `data.enrich_person`
- **Rhumb provider slug:** `people-data-labs`
- **Control target:** `GET https://api.peopledatalabs.com/v5/person/enrich`
- **Artifact:** `artifacts/runtime-review-20260329T070657Z-pdl-firecrawl.json`

### Result

**PASS.** Rhumb Resolve still succeeds in production after the slug-normalization fix that shipped in `94c8df8`.

### Verification notes

- Rhumb estimate returned `GET /v5/person/enrich` with managed credentials.
- Rhumb execution returned **200**.
- Direct PDL control returned **200**.
- Sample parity confirmed on:
  - `full_name`
  - `job_title`
  - `job_company_name`
  - `linkedin_url`

### Investigation note

The first rerun attempt produced a false negative because the test payload used `input` instead of the execution route's supported `params/body` fields. I traced that through `packages/api/routes/capability_execute.py` and confirmed the route was behaving correctly; the bad request shape caused the apparent failure, not a Rhumb regression.

---

## Mission 1 — Firecrawl Phase 3 runtime verification

- **Provider:** `firecrawl`
- **Capability:** `scrape.extract`
- **Control target:** `POST https://api.firecrawl.dev/v1/scrape`
- **Runtime review published:** `ea89cdcb-96e3-46be-83d2-06848323f345`
- **Evidence record:** `6d243eb9-8a33-4286-b626-9929d02fabdc`
- **Artifact:** `artifacts/runtime-review-20260329T070657Z-pdl-firecrawl.json`
- **Coverage audit after publish:** `artifacts/callable-review-coverage-2026-03-29-after-firecrawl-review.json`

### Result

**PASS.** Rhumb-managed `scrape.extract` matched direct Firecrawl control on the same Rhumb blog URL.

### Comparison

Target URL:
`https://rhumb.dev/blog/how-to-evaluate-apis-for-agents`

- Rhumb execution: **200**
- Direct control: **200**
- Matching checks:
  - page title matched
  - markdown prefix matched

### Coverage impact

Firecrawl runtime-backed review coverage moved from:

- **before:** 2 runtime-backed reviews / 7 total reviews
- **after:** 3 runtime-backed reviews / 8 total reviews

---

## Mission 2 — Discovery expansion

Chose **localization** as the next underrepresented high-demand category.

Added migration:
- `packages/api/migrations/0115_localization_expansion_ii.sql`

New services added:
- `smartling`
- `locize`
- `poeditor`
- `weblate`

### Phase 0 assessment

**Best immediate Resolve candidate:** `poeditor`

Reason:
- public callable API
- explicit project/language/upload/export methods
- strong fit for existing `localization.sync` and `localization.export` capability families

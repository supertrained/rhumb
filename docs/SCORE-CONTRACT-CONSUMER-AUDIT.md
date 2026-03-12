# Score Contract Consumer Audit

Updated: 2026-03-12
Owner: Pedro
Status: ACTIVE

## Purpose

Rhumb currently contains **two score-schema lineages**:

1. **Canonical public/product lineage** — `scores`
2. **Legacy engine / SQLAlchemy lineage** — `an_scores` + `dimension_scores`

This audit records where each lineage is still referenced so launch-gate work can converge on one public contract instead of silently rebuilding ambiguity.

## Locked Decision

For launch-gate work and all public/product-facing read surfaces:
- **`scores` is the canonical public read contract**

Implication:
- review/evidence provenance should attach to `scores`
- public docs should describe `scores` as the main read surface
- legacy engine references should be labeled explicitly as internal/legacy, not presented as the default product contract

## Current Consumer Map

### A. Canonical / Product-facing consumers (`scores`)

These are already aligned with the deployed product surface:

- `packages/web/lib/api.ts`
- `packages/api/routes/services.py`
- `packages/api/routes/leaderboard.py`
- `packages/api/routes/search.py`
- `packages/api/migrations/0008_supabase_seed.sql`
- `packages/api/migrations/0009_autonomy_dimensions.sql`
- `packages/api/migrations/0010_seed_autonomy_scores.sql`
- `packages/api/migrations/0011_review_evidence.sql`
- `packages/shared/schema.py`
- `packages/api/FIX-API-ROUTES.md`

### B. Legacy / internal engine lineage (`an_scores`, `dimension_scores`)

These still exist and are not inherently wrong, but they should be treated as legacy/internal until intentionally migrated or retired:

- `packages/api/db/migrations/0001_init.sql`
- `packages/api/db/migrations/0002_score_engine.sql`
- `packages/api/db/models.py`
- `packages/api/db/repository.py`
- `packages/api/routes/scores.py`
- `packages/api/tests/test_scoring_engine.py`
- `packages/api/tests/test_alerts.py`

### C. High-visibility docs that needed clarification

- `docs/API.md` — previously implied the default scoring path persisted to `an_scores` without clarifying the public/product contract split
- `docs/ARCHITECTURE.md` — already updated to describe `scores` as canonical public read surface

## Risks Still Present

### 1. Public/internal ambiguity
A contributor can still read legacy engine files first and assume `an_scores` is the product contract.

### 2. New migration drift
Without an explicit audit, future schema work could accidentally target `an_scores` instead of `scores`.

### 3. Documentation mismatch
If API docs describe legacy internals as current product truth, the repo appears less trustworthy right when launch work depends on credibility.

## Immediate Remediation Completed

### Done in this pass
- locked the public score contract in `docs/CANONICAL-SCORE-CONTRACT.md`
- aligned shared schema references in `packages/shared/schema.py`
- created review/evidence migration spine against `scores` in `packages/api/migrations/0011_review_evidence.sql`
- clarified `docs/API.md` so it no longer presents the legacy `an_scores` lineage as the unqualified public default
- created this audit document to make the remaining split explicit

## Remaining Remediation Queue

### P0
1. **Audit and label remaining high-visibility docs**
   - ensure no public-facing doc implies `an_scores` is the canonical read surface

2. **Apply/backfill review-evidence migration path**
   - move from schema definition to live data path for `evidence_records`, `service_reviews`, and `review_evidence_links`

3. **Expose provenance on product surfaces**
   - service pages should eventually show review/evidence provenance from first-class tables, not only static trust framing

### P1
4. **Decide the fate of `routes/scores.py`**
   Options:
   - keep as explicit legacy/internal scoring engine route
   - adapt it to write/read via canonical product lineage
   - deprecate it once a replacement scoring-write path is defined

5. **Converge or retire SQLAlchemy lineage deliberately**
   - not as a launch-side accident
   - only after product-facing `scores` + review/evidence tables are fully stable

## Operating Rule Going Forward

When adding any new public/product-facing score consumer:
- read from `scores`
- treat `an_scores` / `dimension_scores` as legacy engine lineage unless a deliberate migration plan says otherwise

If a file must reference legacy lineage, label it explicitly as **legacy/internal**.

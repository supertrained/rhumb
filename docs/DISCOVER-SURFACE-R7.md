# Discover Surface Expansion — Round 7 Kickoff (WU 1.5)

> Status: ACTIVE (kickoff)
> Owner: Pedro
> Date: 2026-03-05

## Objective

Ship the first public Discover web surface so operators can inspect AN Scores on service pages and browse category leaderboards with live evidence freshness.

This round decomposes WU 1.5 into mergeable thin slices with explicit acceptance checks.

## Scope (Round 7)

- Service profile pages (AN Score + Execution/Access subscores + explanation + failure modes)
- Category leaderboard pages (ranked services by category)
- Homepage leaderboard module + search entry
- Machine-discovery surfaces (`llms.txt`, structured metadata baseline)

## Out of Scope (for this round)

- Provider claim flows
- Certification enrollment UX
- Full observability dashboarding

## Dependencies

- Existing API endpoints from Rounds 4-6 (`/v1/score`, `/v1/leaderboard`, `/v1/find`)
- Seed dataset quality from scored services

## Thin-Slice Plan

### Slice A — Data contracts + route scaffold
**Branch:** `feat/r7-slice-a-web-contracts`

Deliverables:
- Define typed web data adapters for score/leaderboard payloads
- Create Next.js route scaffold:
  - `/` (homepage shell)
  - `/leaderboard/[category]`
  - `/service/[slug]`
- Add contract tests for adapter parsing of current API payload shapes

Acceptance:
- Contract tests pass for representative fixtures
- Route skeletons render without runtime errors

### Slice B — Leaderboard pages
**Branch:** `feat/r7-slice-b-leaderboard-pages`

Deliverables:
- Category leaderboard UI with rank, aggregate score, execution/access badges, freshness timestamp
- Empty/error states for API fetch failures
- Query param support for category + limit

Acceptance:
- `/leaderboard/payments` renders ranked data from API
- Empty-state + error-state snapshots covered in tests

### Slice C — Service profile pages
**Branch:** `feat/r7-slice-c-service-pages`

Deliverables:
- `/service/[slug]` page with:
  - aggregate + Execution/Access breakout
  - confidence tier + evidence freshness
  - contextual explanation
  - failure mode list
- Alternative links section when available

Acceptance:
- Stripe fixture renders full score breakdown and explanation
- Missing-service response maps to not-found state

### Slice D — Homepage + machine-discovery metadata
**Branch:** `feat/r7-slice-d-home-metadata`

Deliverables:
- Homepage hero + search entry + top leaderboard preview
- `llms.txt` baseline export for machine discovery
- JSON-LD/metadata baseline on service + leaderboard pages

Acceptance:
- `/` renders without blocking API failures
- Metadata output validated in page tests

## Definition of Done (Round 7)

- All four slices merged to `main`
- Web docs updated with route map + local run instructions
- `packages/web` tests green in CI
- Diff artifact generated for each merge PR (viewer URL attached)

## Risks + Mitigations

- **Risk:** API contract drift breaks web parsing
  - **Mitigation:** typed adapters + fixture contract tests in Slice A
- **Risk:** sparse dataset causes weak leaderboard UX
  - **Mitigation:** resilient empty states and category fallback copy in Slice B
- **Risk:** metadata quality regresses under route churn
  - **Mitigation:** metadata assertions in Slice D page tests

## Execution Order

Slice A → Slice B → Slice C → Slice D

Each slice should remain independently mergeable and deploy-safe.

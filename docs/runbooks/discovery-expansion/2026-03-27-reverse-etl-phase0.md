# Reverse ETL Phase 0 note — 2026-03-27

Owner: Pedro / Keel runtime review loop
Status: discovery expansion completed

## Why reverse ETL

Live category counts still showed `reverse-etl` as underrepresented relative to adjacent operational data categories, despite reverse ETL being a real warehouse-to-operations workflow class for CRMs, support systems, and lifecycle tooling.

## Services added

- `portable`
- `hevo-activate`
- `omnata`
- `grouparoo`

Migration:
- `packages/api/migrations/0105_reverse_etl_expansion.sql`

## Phase 0 assessment

### Best immediate Resolve candidate: Portable

Why:
- public admin API documentation is available
- explicit API base surface at `https://api.portable.io`
- resource model includes source specs, sources, destinations, and sync-oriented control primitives
- easiest future wedge is read-first operational primitives such as:
  - `sync.list`
  - `sync.get`
  - `destination.list`
  - `connector.list`

Portable is the clearest service in this batch for a real Resolve Phase 0 once the team wants to push deeper into warehouse-activation workflows.

### Later candidate: Grouparoo

Why later:
- has a REST API and good reverse-ETL semantics
- but is self-hosted / instance-scoped, which weakens access readiness versus Portable
- still strategically useful because self-hosted-heavy teams will care about it

### Coverage additions, not first-wave Resolve targets

#### Hevo Activate
- important vendor to index
- public docs show strong product coverage
- public control surface does **not** currently read like a clean programmable Activate admin API
- catalog value now, weaker first Resolve wedge

#### Omnata
- real reverse-ETL platform with meaningful Snowflake-native depth
- public docs emphasize Snowflake-native app / plugin model more than a clean standalone admin API
- worth indexing now, but not the first Resolve target from this batch

## Recommendation

If reverse ETL gets promoted into the next capability tranche, start with **Portable**.

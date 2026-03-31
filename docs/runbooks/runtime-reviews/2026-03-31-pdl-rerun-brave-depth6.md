# Runtime review loop — PDL rerun + Brave depth 6

Date: 2026-03-31
Owner: Pedro / Keel runtime review loop

## Mission 0 — People Data Labs fix-verify rerun

Prompt priority was explicit: re-run **People Data Labs** first after the slug-normalization fix shipped in commit `94c8df8`.

### Artifact
- `artifacts/runtime-review-pass-20260331T111228Z-pdl-unstructured-depth4.json`

### Execution truth
- Capability: `data.enrich_person`
- Provider requested: `people-data-labs`
- Credential mode: `rhumb_managed`
- Input: LinkedIn profile for Satya Nadella

### Result
- Rhumb estimate: **200**
- Rhumb execute wrapper: **200**
- `provider_used`: **`people-data-labs`**
- Rhumb upstream status: **402**
- Direct PDL control: **402**

### Verdict
- The old slug-normalization bug did **not** recur.
- Canonical production routing still resolves to `people-data-labs` correctly.
- Current failure mode is provider-side quota exhaustion (`account maximum / all matches used`) on both Rhumb and direct control.
- No new Rhumb execution-layer fix was required in this pass.

## Mission 1 — Brave Search freshness rerun

### Provider selection
Fresh callable audit before the pass showed:
- callable providers: **16**
- weakest runtime-backed depth: **5**
- weakest bucket size: **11**
- stalest provider in that weakest bucket: **`brave-search-api`**

Pre-pass audit artifact:
- `artifacts/callable-review-coverage-2026-03-31-pre-next-pass.json`

### Implementation note
Added a new reusable operator helper:
- `scripts/runtime_review_brave_depth6_20260331.py`

Also hardened the audit helper:
- `scripts/audit_callable_review_coverage.py`
- change: retry transient 5xx / network failures on public review reads instead of aborting the whole coverage pass immediately

### Runtime verification
Brave Search was re-run through Rhumb Resolve and direct provider control.

Artifacts:
- `artifacts/runtime-review-pass-20260331T112011Z-brave-current-depth6.json`
- `artifacts/runtime-review-publication-2026-03-31-brave-depth6.json`

Execution details:
- Capability: `search.query`
- Query: `LLM observability tools`
- Count: `5`
- Rhumb provider request: `brave-search-api`
- Canonical publish slug: `brave-search`

### Managed vs direct parity
Passed exactly on:
- result count
- top title
- top URL

Published rows:
- evidence `13c38314-292c-4380-9b10-1e4639314509`
- review `7040485f-5259-4949-8b7c-a01c94d7845d`

### Coverage impact
Post-pass audit artifact:
- `artifacts/callable-review-coverage-2026-03-31-post-brave-depth6.json`

Result:
- `brave-search-api` moved **5 → 6** runtime-backed reviews
- weakest callable runtime-backed depth stayed **5**
- weakest bucket shrank **11 → 10**
- next freshness-ordered target is now **`google-ai`**

## Mission 2 — Discovery expansion

Shipped accounting expansion III:
- migration: `packages/api/migrations/0131_accounting_expansion_iii.sql`
- runbook: `docs/runbooks/discovery-expansion/2026-03-31-accounting-expansion-iii.md`

Added providers:
- `freeagent`
- `sage-intacct`
- `business-central`
- `myob`
- `odoo-accounting`

### Phase 0 assessment
Best next Resolve wedge from this batch:
- `invoice.list`
- `invoice.read`
- `customer.list`
- `bill.list`

Best first provider target:
- **FreeAgent**

## Verdict

Mission 0 is complete: PDL was re-verified in production and the normalization fix still holds.
Mission 1 is complete: Brave Search now has a fresh depth-6 runtime-backed review.
Mission 2 is complete: accounting catalog depth increased with five new API-backed providers and a clear next Phase 0 execution wedge.

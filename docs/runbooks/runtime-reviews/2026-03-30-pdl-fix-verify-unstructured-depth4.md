# Runtime review loop — PDL fix verify + Unstructured depth 3→4

Date: 2026-03-30
Owner: Pedro / Keel runtime review loop

## Mission 0 — PDL fix verify (highest priority)

Immediate instruction was to rerun **People Data Labs** after the slug-normalization fix in commit `94c8df8`, and to prove the fix on the canonical production path rather than relying on the old alias workaround.

### What I tested
- created a fresh temp org + temp review agent
- granted only the canonical service slug: `people-data-labs`
- executed `data.enrich_person` through Rhumb Resolve with:
  - provider: `people-data-labs`
  - credential mode: `rhumb_managed`
  - input: `{"profile":"https://www.linkedin.com/in/satyanadella/"}`

### Result
- estimate: **200**
- managed execute: **200**
- provider used: `people-data-labs`
- upstream status: **200**
- execution id: `exec_03e61b48ddb94aee92e0e4ef64f65520`

That confirms the canonical production path works after the normalization fix.

### Control outcome
I also ran a direct provider control against PDL using the same environment credential.

- direct control status: **402**
- error body indicated the PDL account had hit **account maximum / match limit**

This did **not** invalidate the fix verification because Rhumb-managed execution had already succeeded on the canonical path. It only meant I could not do a same-key parity comparison *after* the managed call without tripping provider quota.

### Mission 0 verdict
- **Rhumb bug not reproduced**
- **canonical `people-data-labs` execution works in production**
- direct control was blocked by provider quota, not by Rhumb routing/auth/grant behavior

Artifacts:
- `artifacts/runtime-review-pass-20260330T110658Z-pdl-unstructured-depth4.json`

## Mission 1 — weakest callable provider depth expansion

Fresh callable coverage before the pass still had a weakest bucket at **3 runtime-backed reviews**. After excluding PDL (already verified in Mission 0), the next weakest provider chosen for a real pass was **Unstructured**.

### Runtime pass
- temp org: `org_runtime_review_20260330t111043z_f9bfef85`
- temp review agent: `1b7a7a99-7d01-4dc1-97b2-ce1336ca50b0`
- granted: `unstructured`
- capability: `document.parse`
- provider: `unstructured`
- credential mode: `rhumb_managed`
- input shape:
  - `strategy=fast`
  - one text file: `runtime-review-unstructured-depth4.txt`

### Rhumb vs direct control
Managed execution returned:
- status **200**
- upstream status **200**
- execution id `exec_b047400cb74c4831bf10ab18b7d4ce9d`
- two elements with exact types:
  - `Title`
  - `NarrativeText`

Direct provider control returned:
- status **200**
- same two elements
- same element ordering and count

### Verdict
- exact parity passed on:
  - element count
  - element type ordering
- **Unstructured depth moved 3 → 4**

### Publication
Published trust rows:
- evidence `cfbf75bf-06c2-4fdd-ae16-45be08651b53`
- review `ef42fd8e-5df5-4530-8a25-245045880000`

Artifacts:
- `artifacts/runtime-review-pass-20260330T111043Z-pdl-unstructured-depth4.json`
- `artifacts/runtime-review-publication-2026-03-30-unstructured-depth4.json`

## Fresh-audit note / tooling fix

Immediately after publication, the public service review route still appeared stale on the exact cached path used by the audit script.

I verified this was **not** a bad publish:
- the new evidence and review rows were present in Supabase
- a cache-busted public read (`?x=1` / unique query param) showed the new rows correctly

So the issue was audit freshness, not publication correctness.

### Fix shipped
Patched `scripts/audit_callable_review_coverage.py` with a new:
- `--cache-bust`

This appends a unique query parameter to public reads so just-published runtime rows are visible immediately during the loop.

Fresh post-fix audit result:
- weakest bucket remains depth **3**
- remaining weakest providers:
  - `apify`
  - `e2b`
  - `replicate`

Fresh audit artifact:
- `artifacts/callable-review-coverage-2026-03-30-post-unstructured-depth4-fresh.json`

## Mission 2 — discovery expansion

After verification work, I expanded **forms** again.

Why this category:
- still thin in the live catalog
- very common agent workflow primitive
- already has a real normalized foothold via `forms.collect`

Added five providers:
- `formspree`
- `basin`
- `forminit`
- `formcarry`
- `web3forms`

Phase 0 assessment:
- strongest next wedge remains extending **`forms.collect`**
- strongest first provider target from this batch: **Formspree**
- best follow-on read-first primitive: `submission.list`

Files:
- `packages/api/migrations/0122_forms_expansion_ii.sql`
- `docs/runbooks/discovery-expansion/2026-03-30-forms-expansion-ii.md`

## Summary

This loop did three useful things:
1. **Confirmed the PDL canonical-slug fix works in production**
2. **Moved Unstructured from depth 3 → 4 with a fresh runtime-backed review**
3. **Expanded Forms with five more providers and a clean next Phase 0 wedge**

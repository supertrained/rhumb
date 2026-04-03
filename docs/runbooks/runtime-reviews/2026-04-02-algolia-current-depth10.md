# Algolia runtime review — depth 10 (2026-04-02 PT)

## What this pass did
- Re-ran live callable-review coverage first and confirmed the weakest claim-safe callable bucket was still depth **9**.
- Confirmed **Algolia** was the freshness-ordered oldest member of that weakest bucket.
- Added `scripts/runtime_review_algolia_depth10_20260402.py` for a reusable production parity pass.
- Ran the pass through Railway production context against Rhumb Resolve and direct Algolia control.

## Production result
- Capability: `search.autocomplete`
- Provider: `algolia`
- Index: `rhumb_test`
- Query: `runtime test`
- Estimate: `200`
- Rhumb execute: `200`
- Direct Algolia control: `200`
- Execution ID: `exec_69f94bf2add44cd88a9311bbe0270f78`

## Parity fields checked
- `nbHits`
- echoed `query`
- top hit `objectID`
- top hit `name`

## Observed parity
- Rhumb and direct control both returned:
  - `nbHits = 1`
  - `query = runtime test`
  - top `objectID = 1`
  - top `name = Rhumb Runtime Test`
- Published trust rows:
  - evidence `48851f7a-a557-41ae-bd73-e7ebe97d040f`
  - review `b9726c82-9165-489e-ac08-7152d3917a96`

## Harness note worth preserving
- The first attempt false-failed because the fresh temp review key hit a transient estimate-path `401 Invalid or expired Rhumb API key` immediately after agent creation/grant.
- The execution path and direct control were already green.
- The harness was corrected by mirroring the post-grant propagation delay + transient invalid-key estimate retry pattern already used in the PDL/Twilio review rails.
- The clean rerun passed on the same production lane after that fix.

## Coverage impact
- **Algolia moved from 9 → 10 claim-safe runtime-backed reviews.**
- The weakest callable-review depth stays **9**.
- The new weakest callable bucket is:
  - `github`
  - `slack`
  - `stripe`
  - `twilio`
- Freshness-ordered next target is now **GitHub**.

## Artifacts
- `artifacts/callable-review-coverage-2026-04-02-pre-algolia-current-pass-from-cron-2149.json`
- `artifacts/runtime-review-pass-20260403T044212Z-algolia-depth10.json`
- `artifacts/runtime-review-publication-2026-04-02-algolia-depth10.json`
- `artifacts/callable-review-coverage-2026-04-02-post-algolia-current-pass-from-cron-2149.json`

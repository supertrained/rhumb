# Callable review coverage audit

Date: 2026-03-27
Owner: Pedro / Keel runtime review loop
Priority: Phase 3 callable-provider verification hygiene
Status: ✅ SHIPPED

## Why this ship mattered

Keel runtime reviews already proved that all 16 callable providers are live, but the loop still needed a deterministic way to answer a simple operational question:

**Which callable provider is actually the weakest on the public runtime-backed trust surface right now?**

That question had been answered manually in prior passes by querying `GET /v1/proxy/services` and then eyeballing each `/v1/services/{slug}/reviews` route. That works for one-off loops, but it is too brittle for a repeatable operating system.

I also hit a real blocker earlier in the day: the host-side `sop` / 1Password service-account path is degraded (`403 Forbidden (Service Account Deleted)`), which means some direct-provider parity reruns cannot be completed on demand. In that state, I still need an honest public-coverage audit instead of guessing.

## What shipped

New script:
- `rhumb/scripts/audit_callable_review_coverage.py`

Artifact generated from live production:
- `rhumb/artifacts/callable-review-coverage-2026-03-27.json`

API trust-surface fix:
- `rhumb/packages/api/routes/reviews.py`
- `rhumb/packages/api/tests/test_review_routes.py`

The script:
1. fetches `GET https://api.rhumb.dev/v1/proxy/services`
2. keeps only `callable=true` providers
3. fetches `GET /v1/services/{slug}/reviews` for each callable provider
4. counts runtime-backed reviews from the public trust labels
5. ranks providers by runtime-backed depth so Mission 1 selection is deterministic

The audit also exposed a real trust-summary bug in the API route: per-service `runtime_backed_pct` was being computed from **evidence records** instead of **runtime-backed reviews / total reviews**. That overstated coverage on services with multiple runtime-linked evidence rows attached to a single review. The route is now fixed in code and covered by a regression test.

Example from the live audit snapshot before deploy:
- `apify` reported `runtime_backed_pct = 100.0`
- but only `1 / 6` public reviews were runtime-backed
- the correct review-level percentage is `16.7%`

## Commands run

```bash
python3 rhumb/scripts/audit_callable_review_coverage.py \
  --json-out rhumb/artifacts/callable-review-coverage-2026-03-27.json

python3 -m pytest rhumb/packages/api/tests/test_review_routes.py -q
```

## Live result snapshot

- **Callable providers audited:** 16
- **Weakest runtime-backed depth:** 1
- **Providers in the weakest bucket:** 10

Weakest bucket:
- `algolia`
- `apify`
- `apollo`
- `brave-search-api`
- `e2b`
- `exa`
- `people-data-labs`
- `replicate`
- `tavily`
- `unstructured`

Strengthened bucket:
- `firecrawl` → 2 runtime-backed reviews
- `google-ai` → 2 runtime-backed reviews

Deep-proof bucket:
- `github` → 6 runtime-backed reviews
- `slack` → 6 runtime-backed reviews
- `stripe` → 6 runtime-backed reviews
- `twilio` → 6 runtime-backed reviews

## Operational conclusion

The callable-review lane is now measurably ranked instead of manually inferred.

The next **true** Mission 1 candidates remain the 10 providers sitting at a single runtime-backed review. But on this host, most of that bucket still depends on direct-provider credential access for same-pass parity controls. Until the `sop` / 1Password path is repaired or another reliable direct-control route is restored, the weakest-bucket reruns remain partially blocked by credential access rather than provider execution quality.

## Why this still counts as forward motion

This ship removed ambiguity from the Keel loop **and** corrected a trust-math bug in the product surface.

Before this tool, "next weakest provider" was a manual claim in a runbook. After this tool, it is a reproducible audit backed by the live public API, and future reruns can prove they advanced the exact weakest bucket rather than a hand-picked provider.

Before the route fix, per-service `runtime_backed_pct` could materially overstate trust coverage. After the fix, the product route now measures the same thing Keel actually cares about: **runtime-backed reviews as a share of published reviews**.

## Next action

Use this audit as the selector for the next callable-provider rerun the moment direct provider credentials are available again. Until then, keep using honest fallback wording when the loop must deviate to the next unblocked public-control lane.

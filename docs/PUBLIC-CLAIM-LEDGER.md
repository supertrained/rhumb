# Public Claim Ledger

Purpose: keep Rhumb's public authority copy aligned with live product truth before distribution. Verdicts use:

- **verified** — backed by live code or shared public truth constants.
- **qualified** — allowed only with explicit scope/condition in the public claim.
- **removed** — stale or unsupported wording removed from public surfaces.

## 2026-04-25 — DC90 claim/schema safety pass

| Claim area | Verdict | Public action | Evidence / source |
| --- | --- | --- | --- |
| Resolve routes by AN Score plus task/runtime factors | verified | Kept the claim, but normalized factor language across homepage, `/resolve`, `/resolve/routing`, `/pricing`, `llms.txt`, shared public truth, and comparison CTA copy to: AN Score, capability fit, provider availability, credential mode, estimated cost, and explicit policy constraints. | `packages/api/services/route_explanation.py` exposes `DEFAULT_WEIGHTS` for `an_score`, `availability`, `estimated_cost`, `latency`, and `credential_mode`; v2 policy supports `pin`, `provider_preference`, `provider_deny`, `allow_only`, and `max_cost_usd`. |
| Provider health / freshness / provider strengths / operator preferences as named routing factors | removed | Removed or replaced unsupported public phrasing with provider availability, estimated cost, and explicit policy constraints. | Public code paths touched: `packages/astro-web/src/lib/public-truth.ts`, `packages/astro-web/src/pages/resolve.astro`, `packages/astro-web/src/pages/resolve/routing.astro`, `packages/astro-web/src/pages/pricing.astro`, `packages/astro-web/src/pages/llms.txt.ts`. |
| Failover as a universal Resolve guarantee | qualified | Replaced `failover` with `supported fallback` or `fallback where a supported alternate is configured`. | Public surfaces touched: homepage governed-key card, pricing page, shared Resolve entity copy. |
| Route receipt fields | qualified | Renamed public routing-page example from generic receipt fields to route-explanation fields and aligned fields to live explanation shape: `winner.provider_id`, `winner.selection_reason`, `candidates[].factors`, `candidates[].policy_checks`, `candidates[].ineligible_reason`, `policy_active`, `strategy`. | `RouteExplanation.to_dict()` and `CandidateExplanation.to_dict()` in `packages/api/services/route_explanation.py`. |
| Callable provider count | verified | Removed hard-coded `16 callable providers` from Resolve hidden/JSON-LD surfaces and now interpolate `PUBLIC_TRUTH.callableProvidersLabel`. | `packages/astro-web/src/lib/public-truth.ts`; `/resolve`; `/resolve/what-is-resolve`. |
| Agent-context and JSON-LD route-factor claims | verified | Kept hidden agent-context and FAQ/JSON-LD visible-equivalent by applying the same qualified routing-factor language used in visible page copy. | `/resolve`, `/resolve/routing`, `/resolve/what-is-resolve`, `llms.txt`. |
| Comparison CTA capability boundary | verified | Kept CTA claim that compared providers listed there have callable paths, while qualifying that final route still depends on requested capability, credential path, estimated cost, and explicit policy constraints. | `packages/astro-web/src/components/ResolveComparisonCta.astro`. |

## Regression guard

`packages/web/tests/public-authority.contract.test.ts` now asserts the updated governed-key wording, Resolve meta description, route-explanation fields, and stale-claim negatives for old `selection_mode`, `alternatives_considered`, `operator preferences`, `freshness, provider health`, and hard-coded `16 callable providers` wording.

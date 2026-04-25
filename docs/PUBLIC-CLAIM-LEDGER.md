# Public Claim Ledger

Purpose: keep Rhumb's public authority copy aligned with live product truth before distribution. Verdicts use:

- **verified** — backed by live code or shared public truth constants.
- **qualified** — allowed only with explicit scope/condition in the public claim.
- **removed** — stale or unsupported wording removed from public surfaces.

## 2026-04-25 — DC90 schema / agent-context anti-cloaking pass

| Claim area | Verdict | Public action | Evidence / source |
| --- | --- | --- | --- |
| Hidden `task fit` routing shorthand | removed | Replaced hidden/schema `task fit` and `task-aligned provider routing` language on Resolve authority surfaces with the visible runtime-backed route contract: supported capability path first, then AN Score, availability / circuit state, estimated cost, credential mode, latency proxy, and explicit constraints. | `docs/PUBLIC-SCHEMA-AGENT-CONTEXT-PARITY.md`; `packages/astro-web/src/lib/public-truth.ts`; `/resolve`; `/resolve/routing`; `/resolve/what-is-resolve`. |
| Agent-context / JSON-LD visible equivalence | verified | Audited homepage, Resolve authority pages, pricing, about, quickstart, trust, leaderboard, `/llms.txt`, and `/llms-full.txt`; machine-readable summaries now summarize visible claims rather than introducing hidden-only routing factors. | `docs/PUBLIC-SCHEMA-AGENT-CONTEXT-PARITY.md`; regression coverage in `packages/web/tests/public-authority.contract.test.ts`. |
| Hard-coded callable count in DC90 machine surfaces | verified | DC90 machine-visible Resolve surfaces continue to use `PUBLIC_TRUTH.callableProvidersLabel` or shared summaries instead of literal stale counts. | `packages/web/tests/public-authority.contract.test.ts` blocks `16 callable providers` across audited DC90 machine surfaces. |

## 2026-04-25 — DC90 route-explanation parity pass

| Claim area | Verdict | Public action | Evidence / source |
| --- | --- | --- | --- |
| Supported capability path as candidate filter | verified | Public copy now says Resolve first matches providers mapped to the supported capability path instead of implying `capability fit` is a serialized route-explanation factor. | `GET /v2/capabilities/search.query/resolve` live read returned provider candidates for the requested capability; `packages/api/services/route_explanation.py` receives capability-specific `mappings`. |
| Runtime route factors | verified | Public route-factor language now names runtime-backed factors: AN Score, availability / circuit state, estimated cost, latency proxy, credential mode, and explicit policy constraints. | `packages/api/services/route_explanation.py` exposes `DEFAULT_WEIGHTS` for `an_score`, `availability`, `estimated_cost`, `latency`, and `credential_mode`; new `test_to_dict_exposes_public_route_factor_contract` freezes serialized factor keys. |
| Policy constraints | verified | Public copy now names only runtime-backed policy constraints: pin, allow list, deny list, and cost ceiling. | v2 policy supports `pin`, `provider_preference`, `provider_deny`, `allow_only`, and `max_cost_usd`; route explanations serialize `pinned`, `denied`, `cost_ceiling_ok`, `quality_floor_ok`, `circuit_healthy`, and `allow_list_ok`. |
| Provider health / freshness / provider strengths / operator preferences as named routing factors | removed | Removed or replaced unsupported public phrasing with provider availability / circuit state, estimated cost, credential mode, latency proxy, and explicit policy constraints. | Public code paths touched: `packages/astro-web/src/lib/public-truth.ts`, `packages/astro-web/src/pages/resolve.astro`, `packages/astro-web/src/pages/resolve/routing.astro`, `packages/astro-web/src/pages/pricing.astro`, `packages/astro-web/src/pages/llms.txt.ts`. |
| Failover as a universal Resolve guarantee | qualified | Replaced `failover` / unqualified `supported fallback` with `fallback where a supported alternate is configured`; constrained safety copy to fail-closed billing / no charge for failed provider calls. | Public surfaces touched: homepage governed-key card, pricing page, shared Resolve entity copy. |
| Route receipt fields | qualified | Public routing-page examples are explicitly route-explanation fields and now include the runtime factor subkeys: `an_score`, `availability`, `estimated_cost`, `latency`, and `credential_mode`. | `RouteExplanation.to_dict()` and `CandidateExplanation.to_dict()` in `packages/api/services/route_explanation.py`; `docs/PUBLIC-ROUTE-EXPLANATION-PARITY.md`. |
| Callable provider count | verified | Removed hard-coded `16 callable providers` from Resolve hidden/JSON-LD surfaces and now interpolate `PUBLIC_TRUTH.callableProvidersLabel`. | `packages/astro-web/src/lib/public-truth.ts`; `/resolve`; `/resolve/what-is-resolve`. |
| Agent-context and JSON-LD route-factor claims | verified | Kept hidden agent-context and FAQ/JSON-LD visible-equivalent by applying the same qualified routing-factor language used in visible page copy. | `/resolve`, `/resolve/routing`, `/resolve/what-is-resolve`, `llms.txt`. |
| Comparison CTA capability boundary | verified | Kept CTA claim that compared providers listed there have callable paths, while qualifying that final route still depends on requested capability, credential path, estimated cost, and explicit policy constraints. | `packages/astro-web/src/components/ResolveComparisonCta.astro`. |

## Regression guard

`packages/web/tests/public-authority.contract.test.ts` now asserts the updated governed-key wording, Resolve meta description, route-explanation fields, factor subfields, and stale-claim negatives for old `selection_mode`, `alternatives_considered`, `operator preferences`, `freshness, provider health`, `Availability and health`, and hard-coded `16 callable providers` wording.

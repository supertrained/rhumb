# Public Schema / Agent-Context Parity — DC90-11

Date: 2026-04-25
Scope: DC90 website/distribution-readiness anti-cloaking audit.

## Rule

Hidden or machine-readable surfaces may summarize visible product truth, but they must not introduce a broader claim than a human can see on the same page or in the paired public machine-readable file.

This applies to:
- `<meta name="description">`, Open Graph, and Twitter summaries;
- JSON-LD `WebPage`, `SoftwareApplication`, and `FAQPage` blocks;
- `data-agent-context` blocks rendered through `Layout.astro`;
- `/llms.txt` and `/llms-full.txt` generated routes.

## Audit result

| Surface | Verdict | Source-backed check |
| --- | --- | --- |
| Homepage `/` | Pass after follow-up | Visible copy says `Index ranks. Resolve routes.`, current callable scope, and best-fit provider framing; agent context summarizes that same Index/Resolve split, and generic Organization JSON-LD now uses the shorter entity description instead of hidden routing-factor detail. |
| `/resolve` | Pass after cleanup | Visible cards/FAQ already expose supported capability matching, AN Score, availability / circuit state, estimated cost, credential mode, latency proxy, explicit constraints, provider pinning, and callable-scope boundary. JSON-LD feature list now says `supported-capability provider routing` instead of the looser `task-aligned provider routing`. |
| `/resolve/routing` | Pass after cleanup | Visible page exposes the route-explanation fields and current runtime-backed factor names. FAQ/meta copy now says Resolve routes by supported capability matching, runtime factors, and explicit constraints — not the broader `task fit` shorthand. |
| `/resolve/what-is-resolve` | Pass after cleanup | Visible lifecycle and boundary sections expose route estimate, credential boundary, budget, provider attribution, and current launchable scope. Agent context now mirrors the runtime-backed factor list without adding `task fit` as a hidden extra claim. |
| `/pricing` | Pass after follow-up | FAQPage JSON-LD is sourced from visible `FAQ` entries; pricing JSON-LD limits itself to governed execution, free discovery, and supported-call routing factors shown on the page. Fallback copy is qualified as `fallback where a supported alternate is configured`, and safety copy is constrained to fail-closed billing / no charge for failed provider calls. |
| `/about` | Pass after follow-up | Person JSON-LD and agent context describe the visible team/operator model and the same Rhumb entity truth shown in the page hero/body. Generic Organization JSON-LD now uses the shorter entity description instead of hidden routing-factor detail. |
| `/quickstart` | Pass | Agent context summarizes the visible free-read → governed-execution path and does not claim universal execution coverage. |
| `/trust` | Pass after follow-up | Agent context summarizes the visible methodology, self-assessment, dispute, evidence, and callable-limitation surfaces without injecting the full Resolve routing-factor contract. |
| `/leaderboard` | Pass after follow-up | Agent context and CollectionPage JSON-LD summarize visible category/scored-service counts. The visible machine-readable summary now also shows the callable-limitation boundary before hidden agent context references it. |
| `/llms.txt` | Pass | Generated route presents Index/Resolve split, route factors, explicit provider pinning, discovery-vs-execution boundary, and authority links using `PUBLIC_TRUTH`. |
| `/llms-full.txt` | Pass after follow-up | Extended generated route reuses `PUBLIC_TRUTH.routingHumanSummary`, `callableRealitySummary`, and authority links instead of adding hidden-only routing factors. Its partial MCP list is labeled as core tools and links back to all 21 tools instead of implying the subset is complete. |

## Cleanup shipped in this slice

- Replaced broad hidden/schema `task fit` / `task-aligned provider routing` phrasing on Resolve authority surfaces with the auditable route contract: supported capability path first, then AN Score, provider availability / circuit state, estimated cost, credential mode, latency proxy, and explicit policy constraints.
- Kept visible page headings aligned by replacing `When task fit beats raw rank` with `When supported routing beats raw rank` and `Three ways task fit changes the answer` with `Three ways supported routing changes the answer`.
- Added regression coverage in `packages/web/tests/public-authority.contract.test.ts` so DC90 machine-readable surfaces cannot reintroduce hidden-only `task fit`, `capability fit`, `operator preferences`, generic `freshness, provider health`, `Availability and health`, `highest-scoring provider`, hard-coded `16 callable providers`, unqualified fail-closed execution-safety, or hidden-only full Resolve-routing context on generic trust/about/home surfaces.
- Follow-up audit fixed public authority count drift by aligning `agent-capabilities.json`, `.well-known/agent-capabilities.json`, static `llms.txt`, the Next static `llms.txt`, README, and Next `PUBLIC_TRUTH.servicesLabel` with live/public `999` services, `435` capability definitions, and `28` callable providers.

## Boundary

This is a source-backed anti-cloaking pass. It does not assert paid live execution proof. The current executable examples remain bounded by the route-explanation parity note in `docs/PUBLIC-ROUTE-EXPLANATION-PARITY.md`.

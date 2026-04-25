# DC90 Resolve Content + Measurement Pack

Date: 2026-04-25
Owner: Pedro
Primary operator: Beacon
Review gates: Keel for factual claims, Helm for executable examples / runtime rails

## Purpose

Package the current owned Resolve authority surfaces into distribution-ready briefs and a measurement protocol without widening public claims beyond live product truth.

This is a Beacon handoff artifact, not a new product-claim source. If page copy and this pack disagree, source-read the live product surfaces and `PUBLIC_TRUTH` first.

## Current source surfaces

| Surface | Canonical URL | Distribution role | Source-backed truth to preserve |
|---|---|---|---|
| Resolve hub | `https://rhumb.dev/resolve` | Primary revenue / product landing page | Resolve is governed execution for supported capabilities. Agents can ask for the job or pin the supported provider path. |
| What is Resolve? | `https://rhumb.dev/resolve/what-is-resolve` | Definition article seed | `Index ranks. Resolve routes.` Resolve starts before the call: route, estimate, credential boundary, execution receipt, and controls. |
| How Resolve routes calls | `https://rhumb.dev/resolve/routing` | Routing explainer seed | Resolve first matches the supported capability path, then uses AN Score, provider availability / circuit state, estimated cost, credential mode, latency proxy, and explicit policy constraints. |
| Resolve comparisons | `https://rhumb.dev/resolve/compare` | Alternatives / competitor-context seed | Rhumb differs from connector catalogs, tool auth layers, and OAuth plumbing by combining neutral service intelligence with governed execution. |
| Resolve key management | `https://rhumb.dev/resolve/keys` | Credential-management seed | Governed API key for repeat Rhumb-managed execution; BYOK / Agent Vault when operator-owned systems are involved; x402 only when zero-signup per-call payment is the point. |
| Resolve per-call pricing | `https://rhumb.dev/resolve/per-call-pricing` | Pricing explainer seed | Discovery is free. Execution is per-call. Estimate first; spend second. Cost can constrain a route but must not rewrite AN Score. |
| Quickstart | `https://rhumb.dev/quickstart` | Developer proof source | Lowest-heroics path: resolve `search.query`, estimate, then execute through Layer 2 with `X-Rhumb-Key` when funded / authorized. |
| Public truth constants | `packages/astro-web/src/lib/public-truth.ts` | Count and claim source | Current public counts: 999 scored services, 435 capabilities, 28 callable providers, 21 MCP tools; current beachhead is research, extraction, generation, and narrow enrichment. |

## Claim guardrails for every derivative asset

Beacon can adapt structure, examples, and headlines. Do not change these facts without a fresh Keel/Helm pass:

- Say **agent gateway**, **Rhumb Index**, **Rhumb Resolve**, **governed execution**, **supported capabilities**, **callable providers**, **AN Score**, and **call**.
- Use `Index ranks. Resolve routes.` as the system spine.
- Say Resolve routes to the best-fit provider for the call by default; never say it blindly routes to the highest-ranked / top-scoring provider.
- Keep discovery breadth separate from execution coverage: 999 scored services and 435 capabilities are broader than the 28 callable providers.
- Keep the execution beachhead narrow: research, extraction, generation, and narrow enrichment — not full general business-agent automation.
- Qualify fallback as **fallback where a supported alternate is configured**.
- Do not claim public improvement in AI visibility, MEO, retrieval, or citation rate until Beacon has a fresh Month 1 measurement run.
- Do not claim npm `rhumb-mcp@2.0.0` is public; the official registry is intentionally pinned to public npm `0.8.2` until a separate npm release is verified.
- Do not make x402 the default repeat-traffic story. Governed API key / wallet-prefund on `X-Rhumb-Key` is the repeat rail; x402 is for zero-signup per-call payment.
- No benchmark, latency, provider-health, budget-control, or every-call-learning claims unless the underlying artifact shows the evidence and Keel signs off.

## Content floor briefs

### 1. Governed execution definition

- **Working title:** What governed execution means for AI agents
- **Canonical source:** `/resolve/what-is-resolve`, `/resolve`, `/docs#resolve-mental-model`
- **Target query cluster:** governed execution layer for agent tool calling; external API access without managing keys; agent gateway for APIs
- **One-sentence answer:** Governed execution is the layer around an agent call that handles route choice, credential boundary, estimate, execution rail, receipt, spend visibility, and operator constraints.
- **Outline:**
  1. The problem: agents can discover APIs faster than operators can safely give them access.
  2. Rhumb model: Index ranks services; Resolve turns supported capability intent into governed calls.
  3. What is governed: route, credentials, estimate, policy, execution, receipt.
  4. What is not claimed: not every indexed service is executable; not magic unrestricted access.
  5. CTA: start with `search.query` in the quickstart, then bring BYOK / Agent Vault only when touching owned systems.
- **Proof points allowed:** current counts, route-factor list, credential-path list, quickstart flow.
- **Required reviews:** Keel for claim breadth; Helm if code snippets are included.

### 2. Resolve vs Composio / Arcade / Nango

- **Working title:** Resolve is not a connector catalog
- **Canonical source:** `/resolve/compare`
- **Target query cluster:** Resolve vs Composio; Composio alternatives for agents; agent connector catalog vs governed execution
- **One-sentence answer:** Connector catalogs, tool auth layers, and OAuth infrastructure solve real adjacent jobs; Rhumb is strongest when the hard question is which provider an agent should trust, route to, pay, and explain.
- **Outline:**
  1. Job-based comparison, not vendor dunking.
  2. Composio: useful for broad app/action catalog coverage.
  3. Arcade: useful for user-authorized tools and permissioned actions.
  4. Nango: useful for OAuth / sync infrastructure inside a product.
  5. Rhumb: neutral service intelligence + governed execution + route explanations.
  6. Honest boundary: if all you need is one app connection, Rhumb may not be the right layer.
- **Proof points allowed:** Index/Resolve split, route-explanation factors, current callable-provider boundary.
- **Required reviews:** Keel before any competitor claims leave owned pages.

### 3. Three-line web-search Resolve quickstart

- **Working title:** Resolve a web-search capability in three calls
- **Canonical source:** `/quickstart`, README examples, MCP README
- **Target query cluster:** AI agent web search API routing; managed web search API key; search.query Resolve quickstart
- **Safe snippet:**

```bash
API="https://api.rhumb.dev/v1"
curl "${API}/capabilities/search.query/resolve"
curl "${API}/capabilities/search.query/execute/estimate"
```

Optional paid / authorized continuation:

```bash
curl -X POST "${API}/capabilities/search.query/execute" \
  -H "X-Rhumb-Key: rhumb_live_..." \
  -H "Content-Type: application/json" \
  -d '{"body":{"query":"best CRM for seed-stage B2B SaaS","max_results":5}}'
```

- **One-sentence answer:** Resolve first shows the ranked supported-provider route; estimate checks the concrete rail before spend; execution requires the governed key / funding boundary.
- **Claim boundary:** Do not promise this succeeds anonymously. Resolve is the no-auth read path; estimate / execute may require the active rail and authorization.
- **Required reviews:** Helm must validate the snippet before external syndication.

### 4. Per-call pricing explainer

- **Working title:** Why per-call pricing needs explainable routes
- **Canonical source:** `/resolve/per-call-pricing`, `/pricing`, `/resolve/keys`
- **Target query cluster:** pay per call API access for agents; x402 agent payments; API execution pricing for agents
- **One-sentence answer:** Agents should estimate route and rail before spending; cost is an execution constraint, not a service-quality score.
- **Outline:**
  1. Discovery is free; execution is per-call.
  2. Price depends on provider cost, credential mode, route, and operator policy.
  3. Governed API key / wallet-prefund is the repeat rail.
  4. x402 is a zero-signup per-call rail, not the default repeat-traffic story.
  5. BYOK / Agent Vault are provider-controlled paths for operator-owned systems.
  6. Neutrality rule: cost can change the route but must not rewrite AN Score.
- **Required reviews:** Keel for pricing wording; Helm for rail examples.

### 5. Routing + keys explainer

- **Working title:** Route by task fit, not leaderboard purity
- **Canonical source:** `/resolve/routing`, `/resolve/keys`
- **Target query cluster:** multi-provider routing for AI agents; agent credential management; provider routing with policy constraints
- **One-sentence answer:** Resolve first matches the supported capability path, then explains how AN Score, availability / circuit state, estimated cost, latency proxy, credential mode, and explicit policy constraints shaped the selected provider.
- **Outline:**
  1. Why global ranking is not enough for execution.
  2. Candidate set: supported capability path.
  3. Runtime factors: AN Score, availability / circuit state, estimated cost, latency proxy, credential mode.
  4. Operator constraints: pin, allow, deny, max-cost ceiling.
  5. Credential paths can legitimately change the route.
  6. Receipts / explanations show selected path and material factors.
- **Required reviews:** Keel for route-factor parity; Helm if using live receipt examples.

## Monthly measurement protocol v1

### Cadence

- Run monthly, starting with Month 1 after this DC90 pass has been live long enough to index.
- Keep raw transcripts / screenshots / result exports. Summaries without artifacts do not count.
- Score only observable outputs. Do not infer improvement from page launches.

### Query set

Use the 15-query map from the DC90 backlog until Beacon has a reason to revise it.

**Index / hybrid queries**

1. Best API services for AI agents
2. Score and rank APIs for agent compatibility
3. Agent-native service directory
4. MCP-compatible APIs for agents
5. Capability discovery for AI agents
6. Agent credential management
7. API reliability evaluation for agents
8. Agent-native compatibility ratings
9. API discovery and routing layer for agents
10. Package manager for agent services/APIs

**Resolve / revenue queries**

11. Credential management for autonomous agents
12. Multi-provider routing/failover for agents
13. External API access without managing keys
14. Governed execution layer for agent tool calling
15. Managed API access with pay-per-call pricing

### Surfaces to test

Run each query against five LLM/search surfaces chosen by Beacon for the month. Keep the set stable month-over-month where possible. If a surface changes, record the change before running the test.

Month 1 scaffold: `docs/DC90-MONTH1-MEASUREMENT-SETUP-2026-04-25.md` selects the baseline-comparable surfaces (`GPT-4`, `Claude`, `Perplexity`, `Gemini`, `Copilot`) and pre-expands the 75-row scorecard at `docs/dc90-measurement/month1-2026-04/scorecard.csv`.

### Scoring columns

For each query × surface result, capture:

| Column | Values / notes |
|---|---|
| `query_id` | Q1–Q15 |
| `surface` | LLM/search system name and mode |
| `rhumb_mentioned` | yes / no |
| `resolve_mentioned` | yes / no |
| `citation_url` | URL cited or surfaced, if any |
| `citation_type` | owned page / GitHub / MCP registry / external article / social / none |
| `entity_accuracy` | 0–3; 0 wrong, 1 vague, 2 mostly right, 3 correct Index/Resolve split |
| `claim_accuracy` | 0–3; penalize overclaims, stale counts, top-score routing, unsupported universal execution |
| `competitors_named` | comma-separated |
| `composio_present` | yes / no |
| `actionability` | 0–3; can a developer find a next step? |
| `notes` | exact quote or summary with artifact pointer |

### Rollup metrics

- AI recommendation / mention rate: Rhumb mentioned ÷ 75.
- Resolve retrieval rate: Resolve mentioned ÷ 25 on Q11–Q15.
- Owned citation rate: citations to `rhumb.dev`, GitHub, npm, or MCP registry ÷ total Rhumb mentions.
- Entity accuracy average: average `entity_accuracy` where Rhumb is mentioned.
- Claim accuracy average: average `claim_accuracy` where Rhumb is mentioned.
- Composio pressure: Composio present ÷ 25 on Q11–Q15.
- External mention count: distinct non-owned URLs that mention Rhumb, excluding scraped duplicates and low-quality directory spam.

### Month 1 acceptance

Beacon can call the measurement run complete when:

- All 75 query × surface rows have artifacts.
- Keel has reviewed at least all Rhumb-mentioned rows for claim accuracy.
- The scorecard separates diagnostic results from public claims.
- Any public improvement claim is either withheld or tied to the fresh Month 1 artifacts.
- Follow-up actions are specific pages/posts/registry surfaces, not generic “do more SEO.”

## Distribution sequence

1. Finish this owned pack and keep source links stable.
2. Beacon picks one content brief plus the measurement protocol; not all five at once.
3. Helm validates any code / estimate / execute examples before publication.
4. Keel reviews public claims before external syndication.
5. Start with one owned article or DEV.to pilot, not a syndication wave.
6. Measure after indexing; then decide whether to widen.

## Pilot prep status

The first selected external pilot is brief 3: **Three-line web-search Resolve quickstart**. Pedro prepared `docs/DC90-DEVTO-PILOT-PREP-2026-04-25.md` with a DEV.to skeleton, snippet block, claim boundaries, and Helm's hosted API validation notes. The DEV.to-ready draft now lives at `docs/DC90-DEVTO-QUICKSTART-PILOT-DRAFT-2026-04-25.md`; Keel passed the final copy on 2026-04-25 after one scope-tightening edit.

Helm pass summary: `resolve` and `estimate` work as anonymous preflight reads; `execute` requires a paid/authorized rail; the dogfood governed key executed through `brave-search-api` in `rhumb_managed` mode. Keep the external copy explicit that `estimate` can differ from the top provider listed by `resolve` because it represents the concrete execution rail before spend.

## Open follow-ups

- Beacon can use `docs/DC90-DEVTO-QUICKSTART-PILOT-DRAFT-2026-04-25.md` as the final-copy source for exactly one DEV.to pilot post, not a wave.
- Keel has passed the final adapted DEV.to copy; re-review only if Beacon changes the copy before external distribution.
- Beacon should decide the five LLM/search surfaces for Month 1 and store raw artifacts in a durable folder before summarizing.

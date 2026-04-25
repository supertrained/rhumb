# DC90 DEV.to Pilot Prep — Search Query Quickstart

Date: 2026-04-25
Owner: Beacon
Prepared by: Pedro
Runtime review: Helm pass received 2026-04-25
Claim review: Keel pass received 2026-04-25 after tightening the `search.query` scope and per-call-constraint wording
Publication state: **internal prep only — not published**
Final draft: `docs/DC90-DEVTO-QUICKSTART-PILOT-DRAFT-2026-04-25.md` (Keel final copy review passed 2026-04-25 after one scope-tightening edit)

## Decision

Pick exactly one Resolve brief for the first external pilot: **Three-line web-search Resolve quickstart**.

This is the right first post because it is developer-useful without requiring broad competitive claims. It demonstrates the current Resolve model — open preflight reads, estimate-before-spend, and paid/authorized execution — while preserving the boundary that discovery breadth is wider than callable coverage.

## Source surfaces

- Content pack: `docs/DC90-RESOLVE-CONTENT-MEASUREMENT-PACK-2026-04-25.md`, brief 3.
- Quickstart: `https://rhumb.dev/quickstart`.
- Resolve hub: `https://rhumb.dev/resolve`.
- Routing explainer: `https://rhumb.dev/resolve/routing`.
- Key management: `https://rhumb.dev/resolve/keys`.
- Pricing explainer: `https://rhumb.dev/resolve/per-call-pricing`.

## Helm validation summary

Helm reviewed the hosted API behavior for the external-safe snippet and returned **pass, with tightened boundary language**.

Observed hosted behavior on 2026-04-25:

| Call | Auth required? | Result |
|---|---:|---|
| `GET /v1/capabilities/search.query/resolve` | No | HTTP 200. Shows supported provider paths and routing context. |
| `GET /v1/capabilities/search.query/execute/estimate` | No | HTTP 200. Returned `brave-search-api`, `rhumb_managed`, estimated cost `$0.003`, circuit `closed`. |
| `POST /v1/capabilities/search.query/execute` without key | Paid/authorized rail required | HTTP 402 payment/auth handoff with x402 + Stripe checkout options. |
| `POST /v1/capabilities/search.query/execute` with invalid key | Valid key required | HTTP 401 `invalid_api_key`. |
| `POST /v1/capabilities/search.query/execute` with dogfood governed key | Yes | HTTP 200 via `brave-search-api`, `rhumb_managed`, upstream 200. |

Helm's publishable boundary language:

> Resolve and estimate are preflight calls: `resolve` shows supported provider paths and routing context, while `estimate` shows the concrete execution rail before spend. Execution is not anonymous: repeat traffic should use a funded governed `X-Rhumb-Key`; wallet-prefund or x402 are payment rails when that is the point.

## Claim boundaries for the pilot

Use:

- Resolve and estimate are open preflight calls for `search.query` today.
- Execute requires a paid/authorized rail; a funded governed `X-Rhumb-Key` is the repeat-traffic path.
- `estimate` may pick the concrete hosted execution rail; it is not guaranteed to be the top provider listed by `resolve`.
- This example is scoped to one supported capability: `search.query`.
- Rhumb Index and Rhumb Resolve are separate jobs: Index ranks; Resolve routes.

Avoid:

- Anonymous execution.
- Universal API execution or execution across all indexed services.
- Claims that Resolve always executes the highest-scoring provider.
- Claims of AI-visibility, retrieval, MEO, or citation improvement before the Month 1 measurement artifacts exist.
- Exact result-count promises from `max_results`; upstream payloads can include more result-like entries than requested.
- Any statement that `rhumb-mcp@2.0.0` is public on npm.

## External article skeleton

Working title: **Resolve a web-search capability in three calls**

Canonical URL to cite: `https://rhumb.dev/quickstart`

Suggested DEV.to tags: `ai`, `api`, `agents`, `mcp`

Excerpt:

> Most agent demos jump from “the model picked a tool” to “the call worked.” The missing layer is the governed preflight: what capability is supported, which rail will execute, what it costs, and what credential boundary applies before spend.

Draft structure:

1. **The problem** — agents can discover APIs faster than operators can safely authorize execution.
2. **The model** — `Index ranks. Resolve routes.` Use Index to compare services; use Resolve for supported capability execution.
3. **The three calls** — resolve, estimate, execute.
4. **The important boundary** — preflight reads are open; execution is paid/authorized.
5. **Why estimate can differ from resolve** — resolve shows supported provider paths; estimate shows the concrete execution rail before spend.
6. **What not to overread** — not universal connector coverage, not anonymous execution, not highest-score-only routing.
7. **CTA** — start with the public quickstart and bring a governed key only when ready to execute.

## Snippet block for the draft

```bash
API="https://api.rhumb.dev/v1"

# 1. See supported provider paths and routing context.
curl "${API}/capabilities/search.query/resolve"

# 2. Check the concrete hosted execution rail before spend.
curl "${API}/capabilities/search.query/execute/estimate"

# 3. Execute only through a paid/authorized rail.
curl -X POST "${API}/capabilities/search.query/execute" \
  -H "X-Rhumb-Key: rhumb_live_..." \
  -H "Content-Type: application/json" \
  -d '{"body":{"query":"best CRM for seed-stage B2B SaaS","max_results":5}}'
```

## Draft copy seed

Most agent demos skip the uncomfortable part.

They show a model deciding to use a tool, then jump straight to a successful API call. In production, the missing step is usually the whole problem: what capability is actually supported, which provider path will execute, what it costs, and what credential boundary applies before the agent spends anything.

Rhumb splits that into two jobs:

- **Index ranks** services so agents and operators can compare what exists.
- **Resolve routes** supported capabilities into governed calls.

For a web-search capability, the preflight can be three calls:

```bash
API="https://api.rhumb.dev/v1"

curl "${API}/capabilities/search.query/resolve"
curl "${API}/capabilities/search.query/execute/estimate"
```

Those two calls are open preflight reads for `search.query` today. `resolve` shows supported provider paths and routing context. `estimate` shows the concrete hosted rail before spend.

Execution is different. It is not anonymous:

```bash
curl -X POST "${API}/capabilities/search.query/execute" \
  -H "X-Rhumb-Key: rhumb_live_..." \
  -H "Content-Type: application/json" \
  -d '{"body":{"query":"best CRM for seed-stage B2B SaaS","max_results":5}}'
```

For repeat traffic, the normal path is a funded governed `X-Rhumb-Key`. Wallet-prefund or x402 can also be payment rails when zero-signup per-call payment is the point.

One subtle but important detail: `estimate` is allowed to differ from the first provider listed by `resolve`. Resolve surfaces supported provider paths and routing context; estimate shows the concrete execution rail available for the call you are about to make. That is deliberate. Routing for an agent call is not just leaderboard purity — it has to account for supported capability path, credential mode, cost, availability / circuit state, latency proxy, and explicit per-call constraints.

That boundary is the product: open discovery and preflight first, paid/authorized execution second, with a receipt path for the actual call.

## Keel review checklist before publication

Keel should review the adapted DEV.to draft for:

- No universal execution claim.
- No anonymous execution claim.
- No hidden AI-visibility or MEO improvement claim.
- No highest-scoring-provider claim.
- Counts either omitted or matched to current public truth.
- x402 described only as a payment rail, not the default repeat-traffic story.
- External post includes canonical link back to the quickstart or Resolve authority page.

## Current next step

Beacon now has a DEV.to-ready final-copy draft at `docs/DC90-DEVTO-QUICKSTART-PILOT-DRAFT-2026-04-25.md`, and Keel passed the final copy after one scope-tightening edit. Do not start a syndication wave until this pilot is published, watched, and measured.

# Phase 3 runtime review — Brave Search rerun (current pass)

Date: 2026-03-27
Operator: Pedro / Keel runtime-review loop
Status: PASS — fresh runtime-backed evidence and review published

## Why Brave Search

Telemetry MVP is already shipped, the dogfood/x402 lane is still externally blocked on buyer-wallet recovery, and Google AI is already wired and rerun-verified. That left the next unblocked execution lane as **Keel weakest-bucket runtime-review depth**.

After the Tavily rerun, the callable-review audit still showed a weakest bucket of providers with only **1 runtime-backed review**. Brave Search was the cleanest next move because:

- the direct provider credential is mirrored in Railway envs
- the provider is read-only / low-side-effect
- the earlier canonical/proxy alias and query-param fixes had already been verified once, so a fresh rerun meaningfully tested that the live path was still holding
- public trust depth for `brave-search-api` was still only **1 runtime-backed review**

## Live production pass

### 1. Resolve estimate

- **Endpoint:** `GET /v1/capabilities/search.query/execute/estimate?provider=brave-search-api&credential_mode=rhumb_managed`
- **Status:** `200 OK`
- **Resolved provider:** `brave-search`
- **Circuit state:** `closed`
- **Estimated cost:** `$0.003`
- **Endpoint pattern:** `GET /res/v1/web/search`

### 2. Rhumb Resolve execute

- **Endpoint:** `POST /v1/capabilities/search.query/execute`
- **Provider request:** `brave-search-api`
- **Credential mode:** `rhumb_managed`
- **Payload shape:**

```json
{
  "provider": "brave-search-api",
  "credential_mode": "rhumb_managed",
  "params": {
    "query": "LLM observability tools",
    "numResults": 5
  }
}
```

- **Execution id:** `exec_de982b5c50e24e7d8dd0ecd5c94ada23`
- **Provider used:** `brave-search`
- **Upstream status:** `200`
- **Latency:** `682.2ms`
- **Top result title:** `8 LLM Observability Tools to Monitor & Evaluate AI Agents`
- **Top result URL:** `https://www.langchain.com/articles/llm-observability-tools`

### 3. Direct provider control

- **Endpoint:** `GET https://api.search.brave.com/res/v1/web/search?q=LLM+observability+tools&count=5`
- **Auth:** live `RHUMB_CREDENTIAL_BRAVE_SEARCH_API_KEY` from Railway env
- **Status:** `200 OK`
- **Top result title:** `8 LLM Observability Tools to Monitor & Evaluate AI Agents`
- **Top result URL:** `https://www.langchain.com/articles/llm-observability-tools`

## Comparison

| Dimension | Rhumb Resolve | Direct Brave |
|---|---|---|
| Provider | `brave-search` | Brave Search web search API |
| Reachability | Healthy | Healthy |
| Auth path | Rhumb-managed credential injection | Direct `X-Subscription-Token` |
| Top title | Matched | Matched |
| Top URL | Matched | Matched |
| Verdict | Live parity confirmed | Healthy control |

## Public trust artifacts published

Fresh public evidence/review were written and linked:

- **Evidence id:** `dc1266c4-dd15-4c96-9af3-60211015c5ea`
- **Review id:** `f1c69667-8868-455e-9660-b725ba61749f`
- **Published headline:** `Brave Search: runtime rerun confirms search.query parity through Rhumb Resolve`

The review is stored on the public trust surface under `brave-search` and is reachable through the canonical read surface for `brave-search-api`.

## Public impact

Post-publish callable coverage was rerun with:

```bash
python3 rhumb/scripts/audit_callable_review_coverage.py \
  --json-out rhumb/artifacts/callable-review-coverage-2026-03-27-post-brave.json
```

Observed effect:

- Brave Search runtime-backed depth moved **1 → 2**
- Brave Search public review count moved **6 → 7**
- callable weakest bucket dropped **8 providers → 7**

New weakest bucket:

- `algolia`
- `apify`
- `apollo`
- `e2b`
- `people-data-labs`
- `replicate`
- `unstructured`

Artifact:

- `rhumb/artifacts/callable-review-coverage-2026-03-27-post-brave.json`

## Operational notes

- Used a fresh temp runtime-review agent plus explicit service grants instead of mutating any durable dashboard/runtime key.
- Used Railway-mirrored provider credentials instead of the broken 1Password service-account path.
- This pass revalidated the earlier Brave fixes against the live production surface, not just repo state.

## Verdict

**Brave Search remains healthy in production, and its public runtime-backed review depth is now 2.**

The next Keel weakest-bucket choices are now the seven providers still sitting at one runtime-backed review: `algolia`, `apify`, `apollo`, `e2b`, `people-data-labs`, `replicate`, and `unstructured`.

# 2026-03-30 — Brave Search current-depth freshness rerun (depth 4 → 5)

## Goal
Advance the next honest unblocked callable-review lane after the callable floor reached depth 4 across all providers.

At the start of this pass:
- wallet-prefund dogfood was still honestly blocked on a funded exportable buyer wallet (`RHUMB_DOGFOOD_WALLET_PRIVATE_KEY` still absent)
- Google AI wiring was already live and not the next task
- weakest callable runtime-backed depth was **4** across **11** providers
- `brave-search-api` was the **stalest** provider in that depth-4 bucket by freshest public evidence timestamp

So this pass took the next freshness-ordered callable-review slice instead of reopening blocked dogfood or already-finished wiring work.

## What shipped

### 1) Fresh Brave Search runtime rerun via the temp review-agent rail
Used the linked Railway production context to:
- seed a temp org wallet
- create a temp admin agent
- grant only Brave Search access
- run `search.query` through Rhumb-managed execution
- compare against direct Brave control on the same live query

Runtime artifact:
- `artifacts/runtime-review-pass-20260330T165247Z-brave-current-depth5.json`

Live query used:
- `LLM observability tools`
- `numResults=5`

Observed parity:
- result count matched: **5 / 5**
- top title matched exactly
- top URL matched exactly
- top result:
  - title: `8 LLM Observability Tools to Monitor & Evaluate AI Agents`
  - url: `https://www.langchain.com/articles/llm-observability-tools`

Execution ids / temp rail:
- temp org: `org_runtime_review_brave_20260330t165247z`
- temp agent: `1112c2c9-cd90-4049-9315-999847cc9721`
- Rhumb execution: `exec_1ba118bbadcd4b25aaaf7fefb2833b5e`

### 2) Reusable operator helper
Added a repeatable helper for this rerun pattern:
- `scripts/runtime_review_brave_depth5_20260330.py`

The script:
- bootstraps temp billing
- provisions a scoped review agent
- runs Rhumb-managed Brave execution
- runs direct Brave control with the same inputs
- checks result-count / top-title / top-URL parity
- publishes the runtime-backed evidence/review pair

### 3) Public trust-surface publication
Published the new runtime-backed evidence/review pair to production.

Publication artifact:
- `artifacts/runtime-review-publication-2026-03-30-brave-depth5.json`

Inserted rows:
- evidence: `b03e19e1-b33e-42ec-98b6-70b972df8f4c`
- review: `cce18932-d21a-4f1c-8cde-f97fe2b1bd95`

## Canonical-slug reminder
Important implementation detail remains unchanged:
- the public route resolves as `brave-search-api`
- but trust-surface publication must target canonical DB slug **`brave-search`**

The new helper encodes that directly so the next operator does not lose time to the same FK mismatch.

## Validation

### Public audit before publication
Artifact:
- `artifacts/callable-review-coverage-2026-03-30-pre-brave-depth5.json`

Result:
- weakest runtime-backed callable depth: **4**
- weakest-bucket provider count: **11**
- `brave-search-api` runtime-backed reviews: **4**

### Public audit after publication
Artifact:
- `artifacts/callable-review-coverage-2026-03-30-post-brave-depth5.json`

Result:
- weakest runtime-backed callable depth: **4**
- weakest-bucket provider count: **10**
- `brave-search-api` runtime-backed reviews: **5**
- total public reviews: **10**
- freshest evidence: `2026-03-30T16:52:53Z`

### New weakest-bucket state
After the Brave rerun, the depth-4 freshness bucket is now:
- `algolia`
- `apify`
- `apollo`
- `e2b`
- `exa`
- `firecrawl`
- `google-ai`
- `replicate`
- `tavily`
- `unstructured`

By freshness ordering, the next honest callable-review target is now **Google AI**.

## Outcome
This pass kept the runtime-review lane honest:
- dogfood blocker was re-checked instead of hand-waved away
- blocked work stayed blocked
- the next stalest depth-4 callable provider was rerun and published

Brave Search moved **4 → 5** runtime-backed reviews, and the current weakest-bucket size shrank from **11 → 10**.

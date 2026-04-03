# Brave Search runtime review — depth 11 (2026-04-03 PT)

## What this pass did
- Re-ran live callable-review coverage first and checked the real freshness order instead of trusting the stale continuation brief.
- Confirmed the callable floor was still depth **10** across all 16 callable providers.
- Confirmed **Brave Search** was the oldest non-PDL member of the depth-10 bucket on the fresh coverage pull (`2026-03-31T11:20:18Z`), so it was the honest next target.
- Added `scripts/runtime_review_brave_depth11_20260403.py` for a reusable production parity pass.
- Ran the pass through Railway production context against Rhumb Resolve and direct Brave Search control.

## Production result
- Capability: `search.query`
- Provider route: `brave-search-api`
- Canonical provider used: `brave-search`
- Query: `LLM observability tools`
- Result count target: `5`
- Estimate: `200` (after **2** attempts because the first estimate hit the known fresh-key auth propagation race)
- Rhumb execute: `200`
- Direct Brave Search control: `200`
- Execution ID: `exec_a6cb1959de734d8f93b8dd391a4c08b5`

## Parity checked
- result count
- top result title
- top result URL
- top result description
- top-3 URL ordering

## Observed parity
- Rhumb and direct control both returned:
  - top result title = `8 LLM Observability Tools to Monitor & Evaluate AI Agents`
  - top result URL = `https://www.langchain.com/articles/llm-observability-tools`
  - top-3 URLs in the same order:
    1. `https://www.langchain.com/articles/llm-observability-tools`
    2. `https://www.reddit.com/r/LangChain/comments/1neh5sw/what_are_the_best_open_source_llm_observability/`
    3. `https://posthog.com/blog/best-open-source-llm-observability-tools`
- Published trust rows:
  - evidence `0104de70-ccf0-4a92-8d15-8db7dc567b53`
  - review `ab5dfd9a-325a-412a-885d-d98773588342`

## Harness note worth preserving
- Brave did reproduce the same estimate-path fresh-key propagation race already seen on other callable review rails.
- The reusable helper now includes:
  - `POST_GRANT_PROPAGATION_DELAY_SECONDS = 5`
  - bounded retry on the specific `Invalid or expired Rhumb API key` estimate signature
- The passing run succeeded on the second estimate attempt and then passed cleanly end-to-end.

## Coverage impact
- **Brave Search moved from 10 → 11 claim-safe runtime-backed reviews.**
- The callable floor stays **10**.
- Providers now above the floor:
  - `e2b` at 11
  - `brave-search` at 11
- The new weakest callable bucket remains depth **10**, now without Brave Search.
- Freshness-ordered next honest non-PDL target is now **Google AI**.

## Artifacts
- `artifacts/callable-review-coverage-2026-04-03-pre-brave-depth11.json`
- `artifacts/runtime-review-pass-20260403T124859Z-brave-depth11.json`
- `artifacts/runtime-review-publication-2026-04-03-brave-depth11.json`
- `artifacts/callable-review-coverage-2026-04-03-post-brave-depth11.json`

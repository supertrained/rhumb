# 2026-03-29 — Brave Search current-depth publication

## Goal
Advance the next honest unblocked callable-review lane after the Replicate publication close.

At the start of this pass:
- wallet-prefund dogfood was still honestly blocked on a funded exportable buyer EOA
- Google AI wiring was already live and not the next task
- weakest public callable runtime-backed depth was **3** across 11 providers
- `brave-search-api` was one of the weakest-bucket providers and had older public runtime evidence than the rest of the bucket

So this pass took a true **3 → 4** depth-expansion slice instead of reopening finished work.

## What shipped

### 1) Fresh Brave Search runtime pass via the temp review-agent rail
Used the linked Railway production context to:
- seed a temp org wallet
- create a temp admin agent
- grant only Brave Search access
- run `search.query` through Rhumb-managed execution
- compare against direct Brave control on the same live query

Runtime artifact:
- `artifacts/runtime-review-pass-20260330T022722Z-brave-current-depth4.json`

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
- temp org: `org_runtime_review_brave_20260330022722`
- temp agent: `540a5302-839b-47ef-b75b-7a382b01f386`
- Rhumb execution: `exec_2deaf987317249cfa31bf9231a624c5b`

### 2) Public trust-surface publication
Published the new runtime-backed evidence/review pair to production.

Publication artifact:
- `artifacts/runtime-review-publication-2026-03-29-brave-depth4.json`

Inserted / reused rows:
- evidence: `a1ef1aa6-bd13-4e16-999b-28b73b44d115`
- review: `e19e0fe2-813b-4f3a-be3d-c2c8054cff0e`

### 3) Canonical-slug gotcha documented
Important implementation detail from this pass:
- the public route resolves as `brave-search-api`
- but `publish_runtime_review_pair.py` had to publish against canonical DB slug **`brave-search`**
- attempting to publish with `brave-search-api` failed FK validation because `services.service_slug` is canonicalized to `brave-search`

This is now captured in the artifact and in this runbook so the next operator does not lose time on the same mismatch.

## Commands used

### Runtime pass
Executed through `railway run -s rhumb-api` with a temp org / temp agent flow and direct Brave control parity check.

The key managed execute body was:

```json
{
  "provider": "brave-search-api",
  "credential_mode": "rhumb_managed",
  "params": {
    "query": "LLM observability tools",
    "numResults": 5
  },
  "interface": "runtime_review"
}
```

### Publication command (canonical slug)
```bash
railway run -s rhumb-api python3 scripts/publish_runtime_review_pair.py \
  --service brave-search \
  --headline "Brave Search: current-depth rerun confirms search.query parity through Rhumb Resolve" \
  --summary "Fresh current-depth runtime rerun passed for Brave Search search.query through Rhumb Resolve. Managed and direct executions matched on result count, top title, and top URL for the same live query." \
  --evidence-title "Brave Search current-depth runtime rerun parity check via Rhumb Resolve" \
  --evidence-summary "Fresh current-depth runtime rerun passed for Brave Search search.query through Rhumb Resolve. Managed and direct executions matched on result count, top title, and top URL for the same live query." \
  --source-ref runtime-review:brave-search:20260330T022722Z \
  --source-batch-id runtime-review:brave-search:20260330T022722Z \
  --reviewed-at 2026-03-30T02:27:22.867967Z \
  --fresh-until 2026-04-29T02:27:22.867967Z \
  --reviewer-agent-id 540a5302-839b-47ef-b75b-7a382b01f386 \
  --agent-id 540a5302-839b-47ef-b75b-7a382b01f386 \
  --run-id exec_2deaf987317249cfa31bf9231a624c5b \
  --tag runtime_review \
  --tag brave-search \
  --tag search.query \
  --tag current_pass \
  --tag phase3 \
  --raw-payload-file artifacts/runtime-review-pass-20260330T022722Z-brave-current-depth4.json \
  > artifacts/runtime-review-publication-2026-03-29-brave-depth4.json
```

## Validation

### Public audit before publication
Artifact:
- `artifacts/callable-review-coverage-2026-03-29-pre-brave-depth4.json`

Result:
- weakest runtime-backed callable depth: **3**
- weakest-bucket provider count: **11**
- `brave-search-api` was still in that bucket at depth **3**

### Public audit after publication
Artifact:
- `artifacts/callable-review-coverage-2026-03-29-post-brave-depth4.json`

Result:
- weakest runtime-backed callable depth: **3**
- weakest-bucket provider count: **10**
- `brave-search-api` now sits at depth **4** with **9** total public reviews

### Public endpoint spot-check
`GET https://api.rhumb.dev/v1/services/brave-search-api/reviews`

Observed after publication:
- total reviews: **9**
- newest headline: `Brave Search: current-depth rerun confirms search.query parity through Rhumb Resolve`
- newest review status: `published`

## Artifacts
- `artifacts/runtime-review-pass-20260330T022722Z-brave-current-depth4.json`
- `artifacts/runtime-review-publication-2026-03-29-brave-depth4.json`
- `artifacts/callable-review-coverage-2026-03-29-pre-brave-depth4.json`
- `artifacts/callable-review-coverage-2026-03-29-post-brave-depth4.json`

## Outcome
This pass did real depth expansion, not bookkeeping cleanup.

Public weakest callable runtime-backed depth stays at **3**, but the weakest bucket shrank from **11 → 10** providers and Brave Search moved up to depth **4**.

The next honest unblocked lane remains the same pattern:
- re-check whether funded EOA dogfood is truly available
- if not, take another weakest-bucket callable provider from **3 → 4**
- do not reopen Google AI wiring or speculative facilitator work

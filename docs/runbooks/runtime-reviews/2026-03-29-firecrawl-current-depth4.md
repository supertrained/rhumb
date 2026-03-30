# 2026-03-29 — Firecrawl current-depth publication

## Goal
Advance the next honest unblocked callable-review lane after re-checking the buyer-wallet dogfood blocker.

At the start of this pass:
- wallet-prefund dogfood was still blocked on a funded exportable buyer EOA
- telemetry MVP was already done
- Google AI, Brave Search, and Tavily were already moved above the weakest callable bucket at depth 4
- the live callable audit showed weakest runtime-backed callable depth **3** across **8** providers
- `firecrawl` was still in that weakest bucket and had the oldest public runtime-backed evidence in the remaining group

So this pass took a real **3 → 4** depth-expansion slice instead of reopening already-cleared work.

## What shipped

### 1) Fresh Firecrawl runtime pass via the temp review-agent rail
Used the linked Railway production context to:
- seed a temp org wallet with `5000` cents
- create a temp admin review agent
- grant only Firecrawl access
- run `scrape.extract` through Rhumb-managed execution
- compare against direct Firecrawl control on the same live Rhumb blog URL
- disable the temp review agent after the pass

Runtime artifact:
- `artifacts/runtime-review-pass-20260330T062735Z-firecrawl-current-depth4.json`

Live target used:
- URL: `https://rhumb.dev/blog/how-to-evaluate-apis-for-agents`
- formats: `markdown`

Observed parity:
- exact page title matched
- exact markdown prefix matched on the first 240 chars
- Rhumb-managed upstream status: **200**
- direct Firecrawl status: **200**

Execution / temp rail:
- temp org: `org_runtime_review_firecrawl_20260330t062735z`
- temp agent: `5d8e8301-412b-47da-9b36-a61fb687fb96`
- Rhumb execution: `exec_bc1f73469b5b46d7ae942a212e6b36e1`

### 2) Public trust-surface publication
Published the new runtime-backed evidence/review pair to production.

Publication artifact:
- `artifacts/runtime-review-publication-2026-03-29-firecrawl-depth4.json`

Inserted rows:
- evidence: `5b31d095-2951-49e4-ae8a-c10855da4e0f`
- review: `2958cd5e-a85a-4f6a-927b-0b5f81d35583`
- primary link row inserted between the new evidence and review

### 3) Public verification artifacts
- pre-audit: `artifacts/callable-review-coverage-2026-03-30-pre-firecrawl.json`
- post-audit: `artifacts/callable-review-coverage-2026-03-30-post-firecrawl-depth4.json`
- review endpoint spot-check: `artifacts/firecrawl-reviews-spotcheck-2026-03-30.json`

## Commands used

### Runtime pass
Executed through the linked Railway production env using a temp org / temp agent flow and direct Firecrawl control parity check.

The managed execute body was:

```json
{
  "provider": "firecrawl",
  "credential_mode": "rhumb_managed",
  "body": {
    "url": "https://rhumb.dev/blog/how-to-evaluate-apis-for-agents",
    "formats": ["markdown"]
  },
  "interface": "runtime_review"
}
```

### Publication command
```bash
railway run -s rhumb-api python3 scripts/publish_runtime_review_pair.py \
  --service firecrawl \
  --headline "Firecrawl: current-depth rerun confirms scrape.extract parity through Rhumb Resolve" \
  --summary "Fresh current-depth runtime rerun passed for Firecrawl scrape.extract through Rhumb Resolve. Managed and direct executions matched on page title and markdown prefix for the same live Rhumb blog URL." \
  --evidence-title "Firecrawl current-depth runtime rerun parity check via Rhumb Resolve" \
  --evidence-summary "Fresh current-depth runtime rerun passed for Firecrawl scrape.extract through Rhumb Resolve. Managed and direct executions matched on page title and markdown prefix for the same live Rhumb blog URL." \
  --source-ref runtime-review:firecrawl:20260330T062735Z \
  --source-batch-id runtime-review:firecrawl:20260330T062735Z \
  --reviewed-at 2026-03-30T06:27:35.854775Z \
  --fresh-until 2026-04-29T06:27:35.854775Z \
  --reviewer-agent-id 5d8e8301-412b-47da-9b36-a61fb687fb96 \
  --agent-id 5d8e8301-412b-47da-9b36-a61fb687fb96 \
  --run-id exec_bc1f73469b5b46d7ae942a212e6b36e1 \
  --tag runtime_review \
  --tag firecrawl \
  --tag scrape.extract \
  --tag current_pass \
  --tag phase3 \
  --raw-payload-file artifacts/runtime-review-pass-20260330T062735Z-firecrawl-current-depth4.json \
  > artifacts/runtime-review-publication-2026-03-29-firecrawl-depth4.json
```

## Validation

### Public audit before publication
Artifact:
- `artifacts/callable-review-coverage-2026-03-30-pre-firecrawl.json`

Result:
- weakest runtime-backed callable depth: **3**
- weakest-bucket provider count: **8**
- `firecrawl` was still in that bucket at depth **3**

### Public audit after publication
Artifact:
- `artifacts/callable-review-coverage-2026-03-30-post-firecrawl-depth4.json`

Result:
- weakest runtime-backed callable depth remains **3**
- weakest-bucket provider count shrank **8 → 7**
- `firecrawl` now sits at depth **4** with **9** total public reviews

Remaining weakest-bucket providers after publish:
- `algolia`
- `apify`
- `apollo`
- `e2b`
- `exa`
- `replicate`
- `unstructured`

### Public endpoint spot-check
`GET https://api.rhumb.dev/v1/services/firecrawl/reviews`

Observed after publication:
- total reviews: **9**
- newest headline: `Firecrawl: current-depth rerun confirms scrape.extract parity through Rhumb Resolve`
- newest review status: `published`
- trust summary runtime-backed pct: `100.0`

## Outcome
This pass did real depth expansion, not bookkeeping cleanup.

Firecrawl moved from public runtime-backed depth **3 → 4**, and the weakest callable bucket shrank from **8 → 7** providers.

The next honest unblocked lane stays the same pattern:
- first re-check whether a funded exportable buyer EOA is actually available for wallet-prefund dogfood
- if not, take another weakest-bucket callable provider from **3 → 4**
- on freshness ordering alone, `algolia` is now the oldest remaining weakest-bucket provider and the next obvious candidate to re-audit

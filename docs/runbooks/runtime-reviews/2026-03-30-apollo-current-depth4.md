# 2026-03-30 — Apollo current-depth publication

## Goal
Advance the next honest unblocked callable-review lane after the Algolia depth-4 pass.

At the start of this pass:
- wallet-prefund dogfood was still honestly blocked on funded exportable buyer-wallet access
- Google AI wiring was already live and not the next task
- weakest public callable runtime-backed depth was **3** across **6** providers
- `apollo` had the stalest freshest runtime-backed evidence inside that weakest bucket

So this pass took a real **3 → 4** depth-expansion slice instead of reopening already-cleared work.

## What shipped

### 1) Fresh Apollo runtime pass via the temp review-agent rail
Used the linked Railway production context to:
- seed a temp org wallet with `5000` cents
- create a temp admin review agent
- grant only Apollo access
- run `data.enrich_person` through Rhumb-managed execution
- compare against direct Apollo control on the same live email input
- disable the temp review agent after the pass

Runtime artifact:
- `artifacts/runtime-review-pass-20260330T082902Z-apollo-current-depth4.json`

Live input used:
```json
{
  "email": "tim@apple.com"
}
```

Observed parity:
- Rhumb-managed wrapper status: **200**
- Rhumb upstream status: **200**
- direct Apollo status: **200**
- matched exactly on:
  - `name`
  - `title`
  - `organization_name`
  - `linkedin_url`
  - `email_status`

Execution / temp rail:
- temp org: `org_runtime_review_apollo_20260330t082902z`
- temp agent: `0103f3f8-f179-4ec3-b79d-5eddf9e2b0dd`
- Rhumb execution: `exec_cb99f67420ec45b0ad4949c03837f749`

### 2) Public trust-surface publication
Published the new runtime-backed evidence/review pair to production.

Publication artifact:
- `artifacts/runtime-review-publication-2026-03-30-apollo-depth4.json`

Inserted rows:
- evidence: `ca5414c5-9fb7-4e34-9420-79b2aca7f2aa`
- review: `aa58d7f2-ea80-49aa-a2dc-0a5c11eed24b`
- primary link row inserted between the new evidence and review

### 3) Public verification artifacts
- pre-audit: `artifacts/callable-review-coverage-2026-03-30-pre-apollo-depth4.json`
- post-audit: `artifacts/callable-review-coverage-2026-03-30-post-apollo-depth4.json`
- review endpoint spot-check: `artifacts/apollo-reviews-spotcheck-2026-03-30.json`

## Commands used

### Runtime pass
Executed through `railway run -s rhumb-api` with a temp org / temp agent flow and direct Apollo control parity check.

The key managed execute shape was:

```json
{
  "provider": "apollo",
  "credential_mode": "rhumb_managed",
  "body": {
    "email": "tim@apple.com"
  },
  "interface": "runtime_review"
}
```

On the live API surface, the execute call used the fixed shorthand form:

```bash
POST /v1/capabilities/data.enrich_person/execute?provider=apollo&credential_mode=rhumb_managed
```

with raw provider-native JSON body:

```json
{
  "email": "tim@apple.com"
}
```

### Publication command
```bash
railway run -s rhumb-api python3 scripts/publish_runtime_review_pair.py \
  --service apollo \
  --headline "Apollo: current-depth rerun confirms data.enrich_person parity through Rhumb Resolve" \
  --summary "Fresh current-depth runtime rerun passed for Apollo data.enrich_person through Rhumb Resolve. Managed and direct executions matched on name, title, organization_name, linkedin_url, and email_status for the same live email input." \
  --evidence-title "Apollo current-depth runtime rerun parity check via Rhumb Resolve" \
  --evidence-summary "Fresh current-depth runtime rerun passed for Apollo data.enrich_person through Rhumb Resolve. Managed and direct executions matched on name, title, organization_name, linkedin_url, and email_status for the same live email input." \
  --source-ref runtime-review:apollo:20260330T082902Z \
  --source-batch-id runtime-review:apollo:20260330T082902Z \
  --reviewed-at 2026-03-30T08:29:02Z \
  --fresh-until 2026-04-29T08:29:02Z \
  --reviewer-agent-id 0103f3f8-f179-4ec3-b79d-5eddf9e2b0dd \
  --agent-id 0103f3f8-f179-4ec3-b79d-5eddf9e2b0dd \
  --run-id exec_cb99f67420ec45b0ad4949c03837f749 \
  --tag runtime_review \
  --tag apollo \
  --tag data.enrich_person \
  --tag current_pass \
  --tag phase3 \
  --raw-payload-file artifacts/runtime-review-pass-20260330T082902Z-apollo-current-depth4.json \
  > artifacts/runtime-review-publication-2026-03-30-apollo-depth4.json
```

## Validation

### Public audit before publication
Artifact:
- `artifacts/callable-review-coverage-2026-03-30-pre-apollo-depth4.json`

Result:
- weakest runtime-backed callable depth: **3**
- weakest-bucket provider count: **6**
- `apollo` was still in that bucket at depth **3**

### Public audit after publication
Artifact:
- `artifacts/callable-review-coverage-2026-03-30-post-apollo-depth4.json`

Result:
- weakest runtime-backed callable depth remains **3**
- weakest-bucket provider count shrank **6 → 5**
- `apollo` now sits at depth **4** with **9** total public reviews

Remaining weakest-bucket providers after publish:
- `apify`
- `e2b`
- `exa`
- `replicate`
- `unstructured`

### Public endpoint spot-check
`GET https://api.rhumb.dev/v1/services/apollo/reviews`

Observed after publication:
- total reviews: **9**
- newest headline: `Apollo: current-depth rerun confirms data.enrich_person parity through Rhumb Resolve`
- newest review status: `published`
- freshest runtime-backed evidence: `2026-03-30T08:29:02Z`

## Outcome
This pass did real depth expansion, not bookkeeping cleanup.

Apollo moved from public runtime-backed depth **3 → 4**, and the weakest callable bucket shrank from **6 → 5** providers.

The next honest unblocked lane stays the same pattern:
- first re-check whether a funded exportable buyer EOA is actually available for wallet-prefund dogfood
- if not, take another weakest-bucket callable provider from **3 → 4**
- on freshness ordering after this pass, **`exa`** is now the stalest remaining weakest-bucket provider

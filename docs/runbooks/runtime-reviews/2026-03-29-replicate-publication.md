# 2026-03-29 — Replicate trust-surface publication

## Goal
Close the remaining public callable-review bookkeeping gap after the successful temp-review-agent rerun in `artifacts/runtime-review-pass-20260329T231345Z-pdl-replicate-current.json`.

At the start of this pass:
- runtime execution was already healthy
- `replicate` was still the sole weakest-bucket callable provider on the **public** trust surface
- the missing step was publication, not another rerun

## What shipped

### 1) Reusable publication helper
Added:
- `scripts/publish_runtime_review_pair.py`

Purpose:
- publish one runtime-backed `evidence_records` row
- publish one matching `service_reviews` row
- create the `review_evidence_links` join row
- stay idempotent on `source_ref` / `source_batch_id`
- run cleanly from the linked Railway production context

### 2) Production publication for Replicate
Command used:

```bash
railway run -s rhumb-api python3 scripts/publish_runtime_review_pair.py \
  --service replicate \
  --headline "Replicate: current-pass rerun confirms ai.generate_text parity through Rhumb Resolve" \
  --summary "Fresh current-pass runtime rerun passed for Replicate ai.generate_text through Rhumb Resolve. Managed and direct executions both created successful predictions and matched on final succeeded state and exact text output." \
  --evidence-title "Replicate current-pass runtime rerun parity check via Rhumb Resolve" \
  --evidence-summary "Fresh current-pass runtime rerun passed for Replicate ai.generate_text through Rhumb Resolve. Managed and direct executions both created successful predictions and matched on final succeeded state and exact text output." \
  --source-ref runtime-review:replicate:20260329T231345Z \
  --source-batch-id runtime-review:replicate:20260329T231345Z \
  --reviewed-at 2026-03-29T23:13:55.412121752Z \
  --fresh-until 2026-04-28T23:13:55.412121752Z \
  --reviewer-agent-id 06b352f9-05f7-4064-9432-c9c8de858276 \
  --agent-id 06b352f9-05f7-4064-9432-c9c8de858276 \
  --run-id exec_c512c7fc9e4c4d35a5f2a675eb71e97c \
  --tag runtime_review \
  --tag replicate \
  --tag ai.generate_text \
  --tag current_pass \
  --tag phase3 \
  --raw-payload-file artifacts/runtime-review-pass-20260329T231345Z-pdl-replicate-current.json \
  > artifacts/runtime-review-publication-2026-03-29-replicate.json
```

Inserted rows:
- evidence: `2a82c5c9-ad10-4ad5-9753-d8173a99f473`
- review: `8ec1f3dc-58d1-4672-8762-d4e032f149ed`
- link: primary review ↔ evidence join created

## Validation

### Public audit before publication
Artifact:
- `artifacts/callable-review-coverage-2026-03-29-pre-replicate-publication.json`

Result:
- weakest runtime-backed callable depth: **2**
- weakest bucket: **replicate**

### Public audit after publication
Artifact:
- `artifacts/callable-review-coverage-2026-03-29-post-replicate-publication.json`

Result:
- weakest runtime-backed callable depth: **3**
- weakest bucket no longer singled out by `replicate`
- the prior public bookkeeping gap is closed

### Public endpoint spot-check
`GET https://api.rhumb.dev/v1/services/replicate/reviews`

Observed after publication:
- total reviews: **8**
- newest headline: `Replicate: current-pass rerun confirms ai.generate_text parity through Rhumb Resolve`
- newest trust label: `🟢 Runtime-verified`
- trust summary runtime-backed pct: `100.0`

## Artifacts
- `artifacts/runtime-review-pass-20260329T231345Z-pdl-replicate-current.json`
- `artifacts/runtime-review-publication-2026-03-29-replicate.json`
- `artifacts/callable-review-coverage-2026-03-29-pre-replicate-publication.json`
- `artifacts/callable-review-coverage-2026-03-29-post-replicate-publication.json`

## Outcome
The honest next unblocked callable-review lane is no longer “rerun Replicate.” That rerun was already done. This pass converted the finished rerun into a real public trust-surface update and removed Replicate as the sole weakest-bucket callable provider.

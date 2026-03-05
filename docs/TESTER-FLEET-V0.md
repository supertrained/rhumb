# Tester Fleet v0 Spec

Status: draft (Round 6 kickoff)
Owner: Pedro
Last updated: 2026-03-04

## Goal

Define a minimal tester-agent fleet that can run repeatable batteries against tool endpoints and emit evidence packets consumable by AN scoring/probe pipelines.

## Scope (v0)

1. **Battery format**
   - YAML-based test battery definition
   - deterministic ordering
   - explicit timeout/retry policy per step
2. **Runner harness**
   - execute battery for a single service target
   - capture per-step outcome, latency, and machine-parseable errors
3. **Evidence output contract**
   - JSON artifact compatible with `POST /v1/score` evidence hydration expectations
4. **Fixture batteries**
   - seed batteries for `health`, `auth`, `schema`, `idempotency`

Out of scope for v0:
- distributed execution across worker pools
- dynamic battery generation by model
- full dashboard/UI

## Battery Schema (YAML)

```yaml
version: 1
service_slug: stripe
profile: default
steps:
  - id: health
    kind: http
    method: GET
    url: https://api.stripe.com/v1/charges?limit=1
    expect_status: [200]
    timeout_ms: 8000
    retries: 1
  - id: schema
    kind: schema_capture
    source_step: health
    fingerprint: semantic_v2
```

### Step kinds (v0)

- `http`: request + response checks
- `schema_capture`: derive `schema_fingerprint_v2` from prior step payload
- `idempotency_check`: replay request with idempotency key and compare response class

## Runner Output Contract

```json
{
  "service_slug": "stripe",
  "battery_version": 1,
  "started_at": "2026-03-05T05:00:00Z",
  "completed_at": "2026-03-05T05:00:03Z",
  "status": "ok",
  "steps": [
    {
      "id": "health",
      "status": "ok",
      "latency_ms": 121,
      "response_code": 200,
      "error": null
    }
  ],
  "summary": {
    "success_rate": 1.0,
    "p95_latency_ms": 121,
    "failures": 0
  }
}
```

## Integration Points

- Persist runner artifacts into probe storage path (`probe_metadata.tester_fleet`) for continuity.
- Feed latency + failure signals into confidence/evidence pipelines.
- Reuse existing schema fingerprinting path to avoid duplicate drift logic.

## Thin Slices

1. **Slice A:** schema + parser for battery YAML (validation + tests)
2. **Slice B:** single-target runner for `http` + `schema_capture`
3. **Slice C:** artifact writer + probe metadata bridge
4. **Slice D:** CLI command `rhumb test-battery <service>`

## Acceptance Criteria

- Can run one battery against one seeded service and produce deterministic artifact output.
- Artifact includes enough telemetry to influence confidence and alert derivation.
- Unit tests cover parser validation and runner happy/error paths.

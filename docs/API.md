# API Reference

## Scoring Endpoint

### `POST /v1/score`

Calculate an AN Score from explicit dimension inputs and persist it to `an_scores`.

**Request body**

```json
{
  "service_slug": "stripe",
  "dimensions": {
    "I1": 9.5,
    "I2": 9.0,
    "I3": 8.5,
    "I4": 9.5,
    "I5": 9.0,
    "I6": 8.0,
    "I7": 9.0,
    "F1": 9.0,
    "F2": 9.5,
    "F3": 9.5,
    "F4": 8.5,
    "F5": 10.0,
    "F6": 9.0,
    "F7": 9.0,
    "O1": 9.0,
    "O2": 9.0,
    "O3": 8.0
  },
  "evidence_count": 72,
  "freshness": "12 minutes ago",
  "probe_types": ["health", "auth", "schema", "load", "idempotency"],
  "production_telemetry": true,
  "probe_freshness": "18 minutes ago",
  "probe_latency_distribution_ms": {"p50": 120, "p95": 340, "p99": 620, "samples": 9},
  "hydrate_probe_telemetry": true
}
```

**Response body**

```json
{
  "service_slug": "stripe",
  "score": 8.9,
  "confidence": 0.98,
  "tier": "L4",
  "tier_label": "Native",
  "explanation": "Stripe scores 8.9 because idempotency supports safe retries, but auth flow friction interrupts agent autonomy.",
  "dimension_snapshot": {
    "dimensions": { "I1": 9.5, "...": 9.0 },
    "raw_weights": { "I1": 0.1, "...": 0.03 },
    "normalized_weights": { "I1": 0.1, "...": 0.03 },
    "category_scores": {
      "infrastructure": 8.9,
      "interface": 9.1,
      "operational": 8.7
    }
  },
  "score_id": "uuid",
  "calculated_at": "2026-03-03T22:11:00+00:00"
}
```

`hydrate_probe_telemetry` is optional. When true, the API auto-hydrates `probe_freshness` and `probe_latency_distribution_ms` from the latest stored probe result when those fields are omitted.

### `GET /v1/services/{slug}/score`

Fetch latest persisted score for a service. For the initial calibration set (`stripe`, `hubspot`, `sendgrid`, `resend`, `github`), this route can bootstrap from hand-scored fixtures when no DB row exists yet.

## Probe Endpoints

### `POST /v1/probes/run`

Run and persist one internal probe.

Example:

```json
{
  "service_slug": "stripe",
  "probe_type": "schema",
  "target_url": "https://status.stripe.com/api/v2/status.json",
  "sample_count": 3,
  "trigger_source": "internal"
}
```

### `POST /v1/probes/schedule/run`

Execute a batch run from seed specs (Stripe/OpenAI/HubSpot).

Example:

```json
{
  "service_slugs": ["stripe", "openai"],
  "sample_count": 3,
  "dry_run": false
}
```

### `GET /v1/services/{slug}/probes/latest`

Fetch the latest persisted probe result for a service (optional `probe_type` query param).

For `probe_type=schema`, metadata includes `schema_signature_version=v2` and `schema_fingerprint_v2`, which are derived from nested response shape descriptors (semantic drift guardrail beyond top-level key lists).

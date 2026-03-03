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
  "production_telemetry": true
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

### `GET /v1/services/{slug}/score`

Fetch latest persisted score for a service. For the initial calibration set (`stripe`, `hubspot`, `sendgrid`, `resend`, `github`), this route can bootstrap from hand-scored fixtures when no DB row exists yet.

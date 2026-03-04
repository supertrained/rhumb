# rhumb-api

FastAPI backend for Rhumb scoring, discovery, and service metadata.

## Run

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn main:app --reload --port 8000
```

## Test

```bash
pytest
```

## Scoring Example (end-to-end)

### 1) Calculate + persist a score

```bash
curl -X POST http://localhost:8000/v1/score \
  -H "Content-Type: application/json" \
  -d '{
    "service_slug": "stripe",
    "dimensions": {
      "I1": 9.5, "I2": 9.0, "I3": 8.5, "I4": 9.5, "I5": 9.0, "I6": 8.0, "I7": 9.0,
      "F1": 9.0, "F2": 9.5, "F3": 9.5, "F4": 8.5, "F5": 10.0, "F6": 9.0, "F7": 9.0,
      "O1": 9.0, "O2": 9.0, "O3": 8.0
    },
    "evidence_count": 72,
    "freshness": "12 minutes ago",
    "probe_types": ["health", "auth", "schema", "load", "idempotency"],
    "production_telemetry": true,
    "hydrate_probe_telemetry": true
  }'
```

Returns:
- `score` (0.0–10.0)
- `confidence` (0.0–1.0)
- `tier` (`L1`–`L4`)
- `explanation` (single sentence, max 150 chars)
- `dimension_snapshot` (raw + normalized dimensions/category rollups)

When `hydrate_probe_telemetry=true`, `/v1/score` auto-loads probe freshness + latency distribution from the latest stored probe if those telemetry fields are omitted in the request.

### 2) Fetch latest score for a service

```bash
curl http://localhost:8000/v1/services/stripe/score
```

This route returns the latest persisted score; if absent, it falls back to hand-scored fixtures for the initial five calibration services.

## Probe Scheduler (WU 1.2)

### Dry run scheduled batch

```bash
curl -X POST http://localhost:8000/v1/probes/schedule/run \
  -H "Content-Type: application/json" \
  -d '{"service_slugs": ["stripe", "openai"], "dry_run": true}'
```

### Execute scheduled batch

```bash
curl -X POST http://localhost:8000/v1/probes/schedule/run \
  -H "Content-Type: application/json" \
  -d '{"service_slugs": ["stripe", "openai", "hubspot"], "sample_count": 3}'
```

### Fetch latest probe for a service

```bash
curl "http://localhost:8000/v1/services/stripe/probes/latest?probe_type=health"
```

Schema probes now persist a semantic shape fingerprint (`schema_fingerprint_v2`) derived from nested response structure, not only top-level keys.

### Cron wiring example

Run every 15 minutes (adjust host/port to deployment):

```bash
*/15 * * * * curl -s -X POST http://localhost:8000/v1/probes/schedule/run -H "Content-Type: application/json" -d '{"sample_count":3}' >/tmp/rhumb-probes.log 2>&1
```

# API Reference

This repo currently contains two score-schema lineages:
- **canonical public/product read surface:** `scores`
- **legacy engine/SQLAlchemy lineage:** `an_scores` + `dimension_scores`

Unless explicitly noted otherwise, public/product-facing read flows should be understood as reading from `scores`.
See `docs/CANONICAL-SCORE-CONTRACT.md` and `docs/SCORE-CONTRACT-CONSUMER-AUDIT.md`.

## Scoring Endpoint

### `POST /v1/score`

Legacy/internal scoring-engine endpoint.

Calculates an AN Score from explicit dimension inputs. In the legacy engine lineage, this path persists score records via the SQLAlchemy-backed scoring layer rather than the canonical public `scores` read surface.

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
  "access_dimensions": {
    "A1": 6.0,
    "A2": 5.5,
    "A3": 6.0,
    "A4": 7.5,
    "A5": 8.0,
    "A6": 8.0
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
  "execution_score": 9.1,
  "access_readiness_score": 8.4,
  "aggregate_recommendation_score": 8.9,
  "an_score_version": "0.2",
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

In v0.2, `score` remains a backward-compatible alias of `aggregate_recommendation_score`.

### `GET /v1/services/{slug}/score`

Fetch the latest persisted score for a service from the current product-facing score surface. For the initial calibration set (`stripe`, `hubspot`, `sendgrid`, `resend`, `github`), this route can bootstrap from hand-scored fixtures when no DB row exists yet.

## Search Endpoint

### `GET /v1/search?q=<query>&limit=<n>`

Search indexed services by free-text query. Used by `rhumb find <query>`.

**Response body**

```json
{
  "data": {
    "query": "payment routing",
    "results": [
      {
        "service_slug": "stripe",
        "name": "Stripe",
        "aggregate_recommendation_score": 8.9,
        "tier": "L4",
        "confidence": 0.95,
        "why": "Best default for payment flows with strong reliability."
      }
    ]
  },
  "error": null
}
```

`limit` is optional and can be used by clients to cap result count.

## Resolve hint contract

`GET /v1/capabilities/{capability_id}/resolve` now returns an `execute_hint` block that is meant to answer the first-success question directly:
- `preferred_provider`: the provider Rhumb wants the operator to use first
- `selection_reason`: machine-readable explanation for why Rhumb chose that provider (`highest_ranked_provider`, `configured_provider_preferred`, `higher_ranked_provider_unavailable`, `higher_ranked_provider_not_execute_ready`, `higher_ranked_provider_mixed_execute_blockers`, or `higher_ranked_provider_filtered_by_credential_mode`)
- `skipped_provider_slugs`: optional higher-ranked providers Rhumb intentionally skipped before choosing the execute path, including providers excluded by a requested `credential_mode`
- `unavailable_provider_slugs`: optional subset of skipped higher-ranked providers that are currently breaker-blocked or otherwise unavailable for execute
- `not_execute_ready_provider_slugs`: optional subset of skipped higher-ranked providers that still rank but cannot back execute in the current context
- `auth_method`: the request-side credential handle (`api_key`, `connection_ref`, `crm_ref`, etc.)
- `configured`: whether that path is already ready on the current deployment in the current context; when `credential_mode` is supplied, this is evaluated against that requested mode rather than some other supported mode
- `credential_modes_url`: machine-readable handoff to the full per-mode setup matrix for this capability
- `preferred_credential_mode`: the lowest-heroics credential mode for that provider in the current context
- `fallback_providers`: optional ordered alternates that can also back execute right now when the preferred path is not the only viable choice
- `setup_hint`: present when `configured=false`, with the exact next setup action Rhumb expects before execute
- `setup_url`: present when Rhumb has a first-class setup surface for that mode, for example a provider ceremony route

`fallback_chain` stays as the ordered ranked shortlist, but now only includes providers that can actually back execute right now in the current context.
Use `GET /v1/capabilities/{capability_id}/credential-modes` when you need the full per-mode matrix. Use `execute_hint` when you want the default next step plus any machine-readable alternates.
If a requested `credential_mode` filters the provider list down to zero, `resolve` now keeps the 200 envelope but adds `recovery_hint.reason=no_providers_match_credential_mode`, `credential_modes_url`, and the unfiltered `supported_provider_slugs` / `supported_credential_modes` so callers can pivot without guessing.
If a requested `credential_mode` still leaves at least one provider, `execute_hint.selection_reason` and `skipped_provider_slugs` now stay honest about any higher-ranked providers that were filtered out, and provider-level plus execute-hint `configured` truth stays scoped to that requested mode so mixed-mode providers do not look preconfigured through the wrong rail.
If a lower-ranked provider is still execute-ready after higher-ranked paths degrade, `execute_hint` now keeps the degraded handoff machine-readable too via `unavailable_provider_slugs`, `not_execute_ready_provider_slugs`, and the mixed blocker selection reason when both conditions apply.
When a requested `credential_mode` dead-ends, whether because zero providers match or because the filtered set collapses to zero execute-ready paths, `resolve` keeps the recovery handoff machine-readable. `supported_provider_slugs` and `supported_credential_modes` still reflect the broader unfiltered pivot, and `recovery_hint.alternate_execute_hint` carries the exact broader-rail execute/setup handoff when Rhumb can already identify one, so callers can pivot without another blind search. In the degraded-but-still-ranked case, `resolve` also keeps the ranked `providers` list while returning `fallback_chain=[]`, `execute_hint=null`, and `recovery_hint.reason=no_execute_ready_providers` plus degraded-provider context like `unavailable_provider_slugs` and `not_execute_ready_provider_slugs`.

## Direct DB-Read Capabilities (AUD-18 Wave 1)

Rhumb now exposes three direct PostgreSQL read-first capabilities:
- `db.query.read`
- `db.schema.describe`
- `db.row.get`

These run through the normal capability surface:
- `GET /v1/capabilities/{capability_id}`
- `GET /v1/capabilities/{capability_id}/resolve`
- `GET /v1/capabilities/{capability_id}/credential-modes`
- `POST /v1/capabilities/{capability_id}/execute`

### Hosted credential posture

For **hosted Rhumb**, the only blessed DB credential path is `credential_mode="agent_vault"`.

- `agent_vault` = preferred: pass a short-lived signed `rhdbv1.` DB vault token in `X-Agent-Token`; compatibility fallback: pass a transient PostgreSQL DSN directly in `X-Agent-Token`, never stored by Rhumb
- `byok` = env-backed `connection_ref` resolution via `RHUMB_DB_<REF>` on the server, intended for self-hosted/internal operator-controlled deployments only

Hosted env-backed `connection_ref` mode is intentionally disabled/hidden right now. If you are calling the hosted product, use `agent_vault`.

### `POST /v1/capabilities/db.query.read/execute`

Execute a bounded, read-only SQL query against the caller's PostgreSQL database.

### Signed token helper (trusted/operator flow)

Use `scripts/build_db_agent_vault_token.py` to mint a short-lived signed `rhdbv1.` token bound to a `connection_ref` and, optionally, an `agent_id` / `org_id`.

```bash
python3 scripts/build_db_agent_vault_token.py \
  --connection-ref conn_app_read \
  --dsn 'postgresql://user:pass@db.example.com:5432/app' \
  --agent-id agent_123 \
  --org-id org_456
```

The script reads the signing secret from `RHUMB_DB_AGENT_VAULT_SECRET` first, then `AUTH_JWT_SECRET` / `RHUMB_ADMIN_SECRET` as fallbacks, matching the DB execute runtime.

**Example request (hosted / `agent_vault`)**

```bash
curl -X POST http://localhost:8000/v1/capabilities/db.query.read/execute \
  -H "Content-Type: application/json" \
  -H "X-Agent-Token: rhdbv1.eyJ..." \
  -d '{
    "credential_mode": "agent_vault",
    "connection_ref": "conn_app_read",
    "query": "select id, email from users order by created_at desc limit 5"
  }'
```

**Example response body**

```json
{
  "data": {
    "capability_id": "db.query.read",
    "credential_mode": "agent_vault",
    "provider_used": "postgresql",
    "row_count": 5,
    "rows": [
      {"id": "u_123", "email": "ada@example.com"}
    ]
  },
  "error": null
}
```

`db.schema.describe` and `db.row.get` share the same hosted credential posture and execution endpoint shape.

## Direct AWS S3 Read-First Capabilities (AUD-18 Wave 1)

Rhumb now exposes three direct AWS S3 read-first capabilities:
- `object.list`
- `object.head`
- `object.get`

These run through the normal capability surface:
- `GET /v1/capabilities/{capability_id}`
- `GET /v1/capabilities/{capability_id}/resolve`
- `GET /v1/capabilities/{capability_id}/credential-modes`
- `POST /v1/capabilities/{capability_id}/execute`

### Credential posture

For the first S3 slice, Rhumb supports **`credential_mode="byok"` only**.

- expected request handle: `storage_ref`
- runtime resolution: env-backed `RHUMB_STORAGE_<REF>` bundle on the server
- current posture: operator-controlled / self-hosted style proofing until a cleaner hosted vault shape exists
- bounded public AWS buckets can also use `auth_mode: "anonymous"` for unsigned reads while still enforcing explicit bucket/prefix allowlists

Bundle shape:

```json
{
  "provider": "aws-s3",
  "auth_mode": "access_key",
  "aws_access_key_id": "AKIA...",
  "aws_secret_access_key": "...",
  "region": "us-west-2",
  "endpoint_url": "https://<optional-s3-compatible-endpoint>",
  "allowed_buckets": ["docs-bucket"],
  "allowed_prefixes": {
    "docs-bucket": ["reports/"]
  }
}
```

`endpoint_url` is optional. Use it only when you need an explicit S3-compatible endpoint override in a bounded operator-proof environment.
`auth_mode` is optional and defaults to `"access_key"`. Set `"anonymous"` only for bounded public AWS proof targets where unsigned reads are intentional.

Use `scripts/build_s3_storage_bundle.py` to generate and validate that bundle against the product runtime parser before setting it on Railway:

```bash
AWS_ACCESS_KEY_ID=... \
AWS_SECRET_ACCESS_KEY=... \
AWS_REGION=us-west-2 \
python3 scripts/build_s3_storage_bundle.py \
  --storage-ref st_docs \
  --bucket docs-bucket \
  --prefix docs-bucket=reports/ \
  --railway
```

That prints the exact `railway variables --set ...` command for `RHUMB_STORAGE_ST_DOCS`.

For a bounded public AWS proof target, use `--anonymous` instead of access-key env vars:

```bash
python3 scripts/build_s3_storage_bundle.py \
  --storage-ref st_docs \
  --anonymous \
  --region us-east-1 \
  --bucket 1000genomes \
  --prefix 1000genomes=1000G_2504_high_coverage/additional_698_related/ \
  --railway
```

### `POST /v1/capabilities/object.list/execute`

List objects within an allowlisted bucket/prefix.

**Example request**

```bash
curl -X POST http://localhost:8000/v1/capabilities/object.list/execute \
  -H "Content-Type: application/json" \
  -H "X-Rhumb-Key: $RHUMB_API_KEY" \
  -d '{
    "credential_mode": "byok",
    "storage_ref": "st_docs",
    "bucket": "docs-bucket",
    "prefix": "reports/",
    "max_keys": 10
  }'
```

### `POST /v1/capabilities/object.head/execute`

Fetch metadata for one allowlisted object.

### `POST /v1/capabilities/object.get/execute`

Fetch a bounded object body for one allowlisted object.

Use `scripts/s3_read_dogfood.py` for the full hosted proof bundle:

```bash
python3 scripts/s3_read_dogfood.py \
  --storage-ref st_docs \
  --bucket docs-bucket \
  --prefix reports/ \
  --key reports/daily.json \
  --summary-only \
  --json-out artifacts/aud18-s3-hosted-proof-<timestamp>.json
```

## Direct Zendesk Ticket Read-First Capabilities (AUD-18 Wave 1)

Rhumb now exposes three direct Zendesk ticket read-first capabilities:

- `ticket.search`
- `ticket.get`
- `ticket.list_comments`

These run through the normal capability surface:

- `POST /v1/capabilities/ticket.search/execute`
- `POST /v1/capabilities/ticket.get/execute`
- `POST /v1/capabilities/ticket.list_comments/execute`

### Credential posture

For the first Zendesk slice, only `credential_mode="byok"` is supported.

Requests must include a `support_ref` that resolves on the server to an env-backed bundle:

- `RHUMB_SUPPORT_<REF>`

Bundle shape:

```json
{
  "provider": "zendesk",
  "subdomain": "acme",
  "auth_mode": "api_token",
  "email": "operator@example.com",
  "api_token": "zd_api_token",
  "allowed_group_ids": [12345],
  "allowed_brand_ids": [67890],
  "allow_internal_comments": false
}
```

Bearer-token mode is also supported by the runtime parser:

```json
{
  "provider": "zendesk",
  "subdomain": "acme",
  "auth_mode": "bearer_token",
  "bearer_token": "zd_bearer_token",
  "allowed_group_ids": [12345],
  "allowed_brand_ids": [67890],
  "allow_internal_comments": false
}
```

### Helper + proof scripts

- Audit local proof sources plus hosted support-surface state before claiming a hosted bundle exists:
  - `python3 scripts/audit_support_proof_sources.py --provider zendesk --summary-only`
- Build and validate the bundle:
  - `python3 scripts/build_zendesk_support_bundle.py --support-ref st_zd --subdomain acme --auth-mode api_token --email you@example.com --api-token "$ZD_API_TOKEN" --allowed-group-id 12345 --allowed-brand-id 67890 --railway`
- Run the hosted proof loop once the bundle is set:
  - `python3 scripts/zendesk_read_dogfood.py --support-ref st_zd --ticket-id 123 --comments-ticket-id 123 --denied-ticket-id 456`

### Example request

```bash
curl -X POST http://localhost:8000/v1/capabilities/ticket.get/execute \
  -H "Content-Type: application/json" \
  -H "X-Rhumb-Key: $RHUMB_API_KEY" \
  -d '{
    "credential_mode": "byok",
    "support_ref": "st_zd",
    "ticket_id": 12345
  }'
```

The runtime enforces:

- group/brand scope via the `support_ref` bundle
- public-comments-only by default
- bounded search and comment limits
- honest provider attribution as `zendesk`

## Pricing Endpoint

### `GET /v1/pricing`

Returns Rhumb's current machine-readable public pricing contract.

**Response body**

```json
{
  "data": {
    "pricing_version": "2026-03-18",
    "canonical_api_base_url": "https://api.rhumb.dev/v1",
    "free_tier": {
      "included_executions_per_month": 1000
    },
    "modes": {
      "rhumb_managed": {
        "margin_percent": 20
      },
      "x402": {
        "margin_percent": 15,
        "network": "Base",
        "token": "USDC"
      },
      "byok": {
        "upstream_passthrough": true,
        "margin_percent": 0
      }
    }
  },
  "error": null
}
```

The pricing contract intentionally omits unfinished volume-discount tiers.

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
  "base_interval_minutes": 30,
  "dry_run": false
}
```

Response includes `cadence_by_service` guardrails with:
- `base_interval_minutes` (clamped to a minimum of 5 and maximum of 1440)
- `next_interval_minutes` (failure-aware exponential backoff)
- `consecutive_failures`
- `jitter_seconds` (deterministic per service)

### `GET /v1/services/{slug}/probes/latest`

Fetch the latest persisted probe result for a service (optional `probe_type` query param).

For `probe_type=schema`, metadata includes `schema_signature_version=v2` and `schema_fingerprint_v2`, which are derived from nested response shape descriptors (semantic drift guardrail beyond top-level key lists).

### `GET /v1/alerts`

Fetch probe-derived drift alerts.

Current primitive alert types:
- `schema_drift` — latest schema fingerprint differs from previous schema probe
- `latency_regression` — p95 health latency regressed beyond threshold versus previous probe

Optional query params:
- `limit` (default 50, max 100)

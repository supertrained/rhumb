# Runbook: Resolve v2 dogfood loop

**Last updated:** 2026-04-07
**Owner:** Pedro

> **Scope note (2026-04-09):** This runbook intentionally exercises the `/v2` Resolve compatibility surface. It is not the public route-authority doc. For current public integration defaults, use `docs/API.md` plus `agent-capabilities.json`.

## Purpose

Prove that the shipped Resolve v2 surface is still coherent under a real operator key.

This runbook exercises the post-build trust loop for the new substrate:

1. `GET /v2/health`
2. `GET /v2/capabilities`
3. optional `GET/PUT /v2/policy`
4. Layer 2 estimate + execute
5. receipt + explanation fetch
6. Layer 1 provider execute
7. billing summary / events
8. trust summary
9. audit status / events
10. receipt-chain verification

If this loop passes, we have fresh proof that the core v2 promises still line up across routing, attribution, receipts, billing, trust, and audit — not just isolated unit tests.

## Script

Operator harness:
- `scripts/resolve_v2_dogfood.py`

## Honest boundary

This runbook is for:
- a **real Rhumb API key** with access to an internal or dedicated dogfood org
- validating the **shipped v2 surface end to end**
- checking **both Layer 2 and Layer 1** against the same capability

This runbook is **not** for:
- public-launch smoke testing without credentials
- publishing npm packages
- x402 wallet / smart-wallet interop verification
- load testing or provider benchmarking

## Prerequisites

### 1) Export a real API key

```bash
export RHUMB_DOGFOOD_API_KEY=rhumb_...
```

Use a dedicated internal dogfood key when possible.

### 1b) Or bootstrap a verifier key through the admin rail

If you are running the loop from automation and do not want to depend on a long-lived dogfood key, the harness can create or rotate a dedicated verifier key first.

It looks for the admin secret in this order:
- `RHUMB_ADMIN_SECRET`
- `RHUMB_ADMIN_KEY`
- 1Password item `Rhumb Admin Secret (Railway)` in vault `OpenClaw Agents`

Example:

```bash
cd rhumb
python3 scripts/resolve_v2_dogfood.py \
  --profile keel \
  --bootstrap-via-admin \
  --json
```

### 2) Refresh a custom Google authorized-user ADC when the BigQuery impersonation lane is blocked on OAuth material

When the warehouse read-first blocker is a missing refresh-capable `authorized_user_json` for the Rhumb Google OAuth client, use the dedicated helper first.

Dry-run it to inspect the exact `gcloud auth application-default login` command and the follow-on bundle command without touching local ADC:

```bash
cd rhumb
python3 scripts/mint_google_authorized_user_adc.py \
  --from-sop-item "Rhumb - Google OAuth" \
  --warehouse-ref bq_analytics_read \
  --service-account-email rhumb-bq-proof-read@rhumb-490802.iam.gserviceaccount.com \
  --billing-project-id rhumb-490802 \
  --location US \
  --allowed-dataset-ref rhumb-490802.analytics_sandbox \
  --allowed-table-ref rhumb-490802.analytics_sandbox.orders \
  --dry-run \
  --json
```

Then rerun without `--dry-run` in a human-attended shell to complete the Google login flow. The helper will:
- source `client_id` + `client_secret` from the shared 1Password item via `sop`
- back up the current `~/.config/gcloud/application_default_credentials.json` if present
- run `gcloud auth application-default login --client-id-file=...` with the requested scopes
- verify that the resulting ADC file is `type=authorized_user` for the intended OAuth client
- print the exact `build_bigquery_warehouse_bundle.py` follow-on command when you provide the bounded warehouse flags above
- print the exact one-shot proof command that rebuilds `RHUMB_WAREHOUSE_<REF>` from the refreshed ADC and runs `bigquery_warehouse_read_dogfood.py` against hosted Rhumb

This helper does **not** update 1Password automatically. Use it to mint/verify the refresh-capable ADC first, then decide whether to store the resulting `authorized_user_json` back into the source item or feed the ADC path directly into the bundle builder.

### 3) Use the product repo Python env

```bash
cd rhumb
python3 scripts/resolve_v2_dogfood.py --help
```

No special virtualenv is required for the script itself; it uses the standard library.

## Default pass

This path is read-heavy and safe by default. It does **not** write org policy unless you ask it to.

```bash
cd rhumb
export RHUMB_DOGFOOD_API_KEY=rhumb_...
python3 scripts/resolve_v2_dogfood.py --json
```

Default execution target:
- capability: `search.query`
- provider: `brave-search`
- credential mode: `rhumb_managed`
- parameters: `{"query":"best AI agent observability tools","numResults":3}`

Default ceiling:
- `max_cost_usd = 0.05`

## Force the Layer 2 provider preference

If you want the Layer 2 pass to explicitly prove policy-driven provider selection for the chosen provider:

```bash
cd rhumb
export RHUMB_DOGFOOD_API_KEY=rhumb_...
python3 scripts/resolve_v2_dogfood.py \
  --force-provider-preference \
  --json
```

## Fleet / multi-agent dogfood profiles

The harness now supports built-in internal profiles so the dogfood loop can tag telemetry by agent lane instead of staying Pedro-only.

List profiles:

```bash
cd rhumb
python3 scripts/resolve_v2_dogfood.py --list-profiles
```

Run one profile with profile-specific defaults for `interface` + `parameters`:

```bash
cd rhumb
python3 scripts/resolve_v2_dogfood.py --profile beacon --json
```

For unattended runs, prefer the admin-bootstrap path so the loop does not silently rot on an expired dogfood key:

```bash
cd rhumb
python3 scripts/resolve_v2_dogfood.py --profile keel --bootstrap-via-admin --json
```

Run the current internal fleet batch (`pedro`, `keel`, `helm`, `beacon`) and capture one consolidated artifact:

```bash
cd rhumb
python3 scripts/resolve_v2_dogfood.py \
  --all-profiles \
  --json \
  --json-out /tmp/resolve-v2-dogfood-fleet.json
```

Current built-in profiles all stay on the proven `search.query` / `brave-search` path, but each emits a distinct interface label:
- `dogfood-pedro`
- `dogfood-keel`
- `dogfood-helm`
- `dogfood-beacon`

This is deliberate: it expands the dogfood loop into per-agent telemetry without pretending the fleet is already exercising a wider stable capability set than we have actually verified.

## Fleet status from latest artifacts

When the recurring non-Pedro lanes are already running and you want a quick steady-state read without hitting live APIs again, audit the latest checked-in artifacts instead:

```bash
cd rhumb
python3 scripts/resolve_v2_dogfood.py \
  --fleet-status \
  --refresh-stale-profiles \
  --bootstrap-via-admin \
  --json-out artifacts/resolve-v2-dogfood-fleet-status-latest.json
```

Default audited lanes:
- `keel`
- `helm`
- `beacon`

Default freshness window:
- `1080` minutes (18 hours)

This mode reads the current `resolve-v2-dogfood-*-admin-latest.json` artifacts, checks whether each lane is still marked `ok`, verifies the receipt-chain flag, and, when `--refresh-stale-profiles` is present, reruns any stale or failed lane once before recomputing the final summary.

## Summary-only mode for recurring proof jobs

For recurring cron lanes, prefer a single-line stdout summary instead of the full human report:

```bash
cd rhumb
python3 scripts/resolve_v2_dogfood.py \
  --profile keel \
  --bootstrap-via-admin \
  --summary-only \
  --json-out artifacts/resolve-v2-dogfood-keel-admin-latest.json
```

The same pattern works for `helm`, `beacon`, and `--fleet-status`.

Use this mode when the job's purpose is strictly mechanical proof refresh:
- write or refresh the latest artifact
- return one compact status line to cron history
- avoid duplicating backlog / memory bookkeeping inside the recurring lane

## Recurring fleet-status audit cron

The consolidated artifact-side audit is now also on a recurring mechanical cron:

- job id: `db54ed12-26ac-4fed-8f95-72b0196f4c90`
- name: `Resolve v2 Dogfood Fleet Status Audit`
- schedule: `10:45` and `22:45` PT

It runs this exact command:

```bash
cd rhumb
python3 scripts/resolve_v2_dogfood.py \
  --fleet-status \
  --refresh-stale-profiles \
  --bootstrap-via-admin \
  --summary-only \
  --json-out artifacts/resolve-v2-dogfood-fleet-status-latest.json
```

Purpose:
- refresh the consolidated `keel` / `helm` / `beacon` proof artifact after the per-profile lanes
- self-heal a stale or failed lane once before the fleet audit locks in a red status
- keep cron history to one compact proof line
- separate mechanical evidence refresh from backlog / memory bookkeeping

## Policy smoke test

Only do this on a dedicated internal dogfood org or key.

```bash
cd rhumb
export RHUMB_DOGFOOD_API_KEY=rhumb_...
python3 scripts/resolve_v2_dogfood.py \
  --policy-provider-preference brave-search-api \
  --policy-max-cost-usd 0.05 \
  --json
```

This will:
- read the current org policy
- write a temporary provider preference / cost ceiling
- confirm the write via `GET /v2/policy`
- continue with the rest of the loop

## Skip Layer 1

If you only want to prove the Layer 2 + trust surfaces:

```bash
cd rhumb
export RHUMB_DOGFOOD_API_KEY=rhumb_...
python3 scripts/resolve_v2_dogfood.py \
  --skip-layer1 \
  --json
```

## Save evidence

```bash
cd rhumb
export RHUMB_DOGFOOD_API_KEY=rhumb_...
python3 scripts/resolve_v2_dogfood.py \
  --json \
  --json-out /tmp/resolve-v2-dogfood.json
```

Capture at minimum:
- Layer 2 `execution_id`
- Layer 2 `receipt_id`
- Layer 2 `explanation_id`
- Layer 1 `execution_id`
- Layer 1 `receipt_id`
- billing `events_count`
- audit `total_events`
- receipt-chain verification result

## Failure triage

### `v2 health failed`
- deploy or API base URL issue
- wrong host / outage

### `v2 policy get failed`
- invalid or expired API key
- identity store / auth regression

### `v2 layer2 estimate failed`
- capability/provider mismatch
- credential mode unavailable
- estimate surface drift

### `v2 layer2 execute failed`
- routing/policy regression
- managed provider unhealthy
- cost ceiling too low
- request schema drift on `parameters`

### `v2 layer2 execute returned no receipt_id`
- receipt wiring regression
- response-shape drift after execution translation

### `v2 layer1 execute failed`
- provider slug mismatch
- L1 route regression
- direct provider execution path unhealthy

### `v2 trust summary failed`
- billing event stream regression
- score-cache regression
- auth issue on trust routes

### `v2 audit status failed`
- audit trail not mounted
- auth issue on audit routes
- chain-state read regression

### `v2 receipt chain verify failed`
- receipt store drift
- chain verification bug
- persistence issue in receipt service

## Operational meaning

When this runbook passes, Rhumb has fresh evidence that:
- v2 health + catalog are reachable
- Layer 2 routing still executes under a real key
- receipts and explanations still connect back to execution
- Layer 1 still works as the exact-provider trust anchor
- billing, trust, and audit surfaces still reflect real execution state
- the receipt chain still verifies

That is the honest repeatable dogfood loop for the shipped Resolve v2 surface.

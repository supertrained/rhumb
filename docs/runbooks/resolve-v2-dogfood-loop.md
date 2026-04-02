# Runbook: Resolve v2 dogfood loop

**Last updated:** 2026-04-02
**Owner:** Pedro

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

### 2) Use the product repo Python env

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

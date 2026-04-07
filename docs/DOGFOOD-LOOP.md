# Dogfood Loop

Rhumb now has a repeatable dogfood harness for internal agents: `examples/dogfood-telemetry-loop.py`.

The goal is simple: generate real Resolve traffic, then verify that the same agent can see those calls in `/telemetry/usage` and `/telemetry/recent`.

## Why this exists

Phase 1 proved the telemetry stack with a disposable internal agent. That was enough to validate the product, but not enough to create an operating loop.

This harness turns that one-off proof into a reusable pattern that any internal agent can run with its own API key.

## What it does

1. Reads a baseline from `GET /telemetry/usage`
2. Resolves a target capability and selects the top N providers
3. Executes a small battery of real calls through Resolve
4. Fetches `GET /telemetry/recent`
5. Confirms the returned `execution_id`s are visible in telemetry

## Default target

The default capability is `search.query`, because it is the safest path for repeatable internal traffic generation.

You can override it with environment variables if you want to test another callable capability.

## Run it

```bash
cd rhumb
pip install httpx
export RHUMB_API_KEY=your_key_here
python examples/dogfood-telemetry-loop.py
```

## Useful knobs

```bash
export RHUMB_DOGFOOD_CAPABILITY=search.query
export RHUMB_DOGFOOD_QUERIES="best ai agents|mcp tool routing|managed credentials"
export RHUMB_DOGFOOD_PROVIDER_COUNT=2
export RHUMB_DOGFOOD_DAYS=1
python examples/dogfood-telemetry-loop.py
```

## Expected outcome

A healthy run should show:

- successful Resolve executions
- a positive call delta in `/telemetry/usage`
- matching execution IDs visible in `/telemetry/recent`

## How to use this operationally

- Give each internal agent its own Rhumb API key
- Run the harness under that agent identity
- Log results into runtime reviews / backed evidence
- For unattended v2 automation, prefer `scripts/resolve_v2_dogfood.py --bootstrap-via-admin` so the loop can create or rotate its verifier key instead of depending on a stale long-lived dogfood key
- For recurring non-Pedro lanes already writing latest artifacts, use `python3 scripts/resolve_v2_dogfood.py --fleet-status --json-out artifacts/resolve-v2-dogfood-fleet-status-latest.json` to audit Keel/Helm/Beacon freshness and chain health without generating another live call
- Expand from `search.query` to other callable capabilities only after the loop is clean

## Expansion order

1. Pedro / operator agents
2. GTM and research agents that can naturally use `search.query`
3. Provider-specific loops once Google AI and other managed configs are wired
4. Keel runtime-review loops for callable providers with weak review coverage

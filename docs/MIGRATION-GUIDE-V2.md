# Rhumb Resolve v2 Migration Guide

## Overview

Rhumb v2 (Resolve) adds three execution layers, deterministic recipes, and comprehensive observability infrastructure. **v1 is fully backward compatible** — nothing breaks. This guide explains what's new and how to adopt v2 features.

## What's NOT changing

- All `/v1/` endpoints continue to work identically
- `execute_capability` via v1 still routes the same way
- API key authentication unchanged
- x402 micropayments unchanged
- `RHUMB_API_KEY` environment variable unchanged

**You do not need to change anything to keep working.** v2 features are additive.

## What's new in v2

### Three Execution Layers

| Layer | Endpoint | When to use |
|-------|----------|-------------|
| **Layer 1** | `POST /v2/providers/{id}/execute` | You know which provider you want. Escape hatch. |
| **Layer 2** | `POST /v2/capabilities/{id}/execute` | Let Rhumb pick the best provider. Default for most use. |
| **Layer 3** | `POST /v2/recipes/{id}/execute` | Multi-step compiled workflows with safety controls. |

### Enhanced responses

All execution responses now include:

```json
{
  "_rhumb": {
    "provider": { "id": "stripe", "an_score": 8.5, "tier": "L4" },
    "layer": 2,
    "receipt_id": "rcpt_...",
    "cost": { "provider_usd": 0.001, "rhumb_usd": 0.0002, "total_usd": 0.0012 },
    "credential_mode": "rhumb_managed"
  }
}
```

Response headers:
- `X-Rhumb-Provider`: Provider slug
- `X-Rhumb-Layer`: 1 or 2
- `X-Rhumb-Receipt-Id`: Immutable receipt ID
- `X-Rhumb-Cost-Usd`: Total billed cost

### Policy controls

Set account-level or per-call execution policies:

```json
// Per-call override
POST /v2/capabilities/{id}/execute
{
  "parameters": { ... },
  "policy": {
    "pin": "stripe",
    "max_cost_usd": 0.01,
    "provider_deny": ["provider-x"]
  }
}

// Account-level policy
PUT /v2/policy
{
  "max_cost_usd": 0.05,
  "provider_preference": ["stripe", "openai"]
}
```

### Execution receipts

Every execution produces a chain-hashed, HMAC-signed receipt:

```
GET /v2/receipts/{receipt_id}
GET /v2/receipts/{receipt_id}/explanation  ← why this provider was chosen
```

### Route explanations

5-factor composite scoring explains every routing decision:
- AN Score (20%)
- Availability (30%)
- Cost (25%)
- Latency (15%)
- Credential preference (10%)

### AN Score (read-only cache)

Scores are served from a structurally separated read-only cache:

```
GET /v2/scores/{provider_id}
GET /v2/scores/{provider_id}/history  ← chain-hashed audit trail
GET /v2/scores/cache/status
```

### Billing events

Chain-hashed billing event stream:

```
GET /v2/billing/events
GET /v2/billing/summary
```

### Trust dashboard

```
GET /v2/trust/summary
GET /v2/trust/providers
GET /v2/trust/costs
GET /v2/trust/reliability
```

### Recipes (Layer 3)

Deterministic, compiled workflows:

```
GET /v2/recipes
GET /v2/recipes/{id}
POST /v2/recipes/{id}/execute
```

Safety controls active on every recipe execution:
- Content firewall at every step transition
- Idempotency key system (no double charges)
- Nesting depth limit (3 levels)
- Fan-out rate limiting
- Per-step budget enforcement

### Audit trail

Append-only, chain-hashed audit log:

```
GET /v2/audit/events
GET /v2/audit/events/{id}
POST /v2/audit/export
GET /v2/audit/verify
GET /v2/audit/status
```

### Kill switches

Administrative safety controls:
- L1: Per-agent kill switch
- L2: Per-provider kill switch
- L3: Per-recipe kill switch
- L4: Global kill switch (two-person auth required)

## MCP tool changes

### New tools in v2.0.0

| Tool | Layer | What it does |
|------|-------|-------------|
| `rhumb_recipe_execute` | L3 | Execute a compiled recipe |
| `rhumb_list_recipes` | L3 | Browse available recipes |
| `rhumb_get_recipe` | L3 | Get recipe details |
| `get_receipt` | All | Retrieve HMAC-signed execution receipt |
| `usage_telemetry` | L2 | Report execution telemetry |

### Updated tools

- `execute_capability` — now returns `_rhumb_v2` metadata with attribution, receipt ID, and route explanation
- `estimate_capability` — now includes per-provider cost breakdown

### Unchanged tools

All 6 discovery tools and all 5 financial tools work identically.

## Upgrade path

1. Update: `npx rhumb-mcp@2` (or update your pinned version)
2. Start using v2 responses — the `_rhumb` block is on every execution
3. Adopt recipes when you need multi-step workflows
4. Use receipts for audit/compliance

No configuration changes needed. No breaking API changes.

## API version endpoints

| Version | Base | Status |
|---------|------|--------|
| v1 | `https://api.rhumb.dev/v1` | Fully supported forever |
| v2 | `https://api.rhumb.dev/v2` | New — all v2 features |

v1 endpoints are not deprecated. They will never be removed (spec decision D3).

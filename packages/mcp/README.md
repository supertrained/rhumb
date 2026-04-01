# Rhumb MCP Server

**Agent-native tool intelligence for the Model Context Protocol.**

Three execution layers: raw provider access (Layer 1), intelligent routing (Layer 2), and deterministic composed recipes (Layer 3, beta). Every provider rated with the AN Score. Every execution produces a chain-hashed receipt.

- Website: https://rhumb.dev
- Docs: https://rhumb.dev/blog/getting-started-mcp
- Pricing: https://rhumb.dev/pricing
- Repo: https://github.com/supertrained/rhumb

## Zero-config quickstart

**No API key needed for discovery.** Install and start immediately:

```bash
npx rhumb-mcp@latest
```

Or add to Claude Desktop / Cursor / any MCP client:

```json
{
  "mcpServers": {
    "rhumb": {
      "command": "npx",
      "args": ["-y", "rhumb-mcp@latest"]
    }
  }
}
```

Ask your agent:
- *"Find me the best email API for agents"*
- *"What's the AN Score for Stripe?"*
- *"Execute a recipe that enriches a contact and sends a welcome email"*

## What's new in v2.0.0

**Rhumb Resolve** — three execution layers:

| Layer | What | How |
|-------|------|-----|
| **Layer 1** | Raw provider access | You pick the provider. Escape hatch + trust anchor. |
| **Layer 2** | Capability routing | Rhumb picks the best provider. Cost-optimal with quality floor. |
| **Layer 3** | Deterministic recipes (beta) | Compiled DAG workflows. Multi-step, budget-enforced, content-firewalled. No published recipes yet. |

**New infrastructure:**
- Execution receipts (chain-hashed, HMAC-signed)
- Route explanations (why this provider was chosen)
- AN Score structural separation (read-only cache, auditable)
- Billing event stream (chain-hashed, 15+ event types)
- Trust dashboard (provider health, costs, reliability)
- Recipe safety controls (content firewall, idempotency, nesting depth, fan-out rate limiting)
- Kill switches (per-agent, per-provider, per-recipe, global with authenticated two-person auth)
- Audit trail (append-only, chain-hash verification, export API)

### Migration from 0.x

- All v1 endpoints remain **fully backward compatible** — no breaking changes
- New v2 endpoints available alongside v1
- `execute_capability` now returns `_rhumb_v2` metadata with attribution and receipts
- New tools for recipes, receipts, and telemetry
- Update: `npx rhumb-mcp@2` (or `npx rhumb-mcp@latest`)

## Discovery tools (no auth, 6 tools)

| Tool | What it does |
|------|-------------|
| `find_services` | Search 1,000+ services by what you need |
| `get_score` | Full AN Score breakdown for any service |
| `get_alternatives` | Find alternatives ranked by score |
| `get_failure_modes` | Known failure patterns + workarounds |
| `discover_capabilities` | Browse capabilities by domain (`email.send`, `payment.charge`) |
| `resolve_capability` | Get ranked providers with health, cost, and routing data |

## Execution tools (auth required, 8 tools)

```json
{
  "mcpServers": {
    "rhumb": {
      "command": "npx",
      "args": ["-y", "rhumb-mcp@latest"],
      "env": {
        "RHUMB_API_KEY": "rk_your_key_here"
      }
    }
  }
}
```

Get a key at https://rhumb.dev/auth/login (GitHub, Google, or email — 30 seconds).

| Tool | What it does |
|------|-------------|
| `execute_capability` | Call a capability through Rhumb Resolve (Layer 2) |
| `estimate_capability` | Get cost before executing (no charge) |
| `recipe_execute` | Execute a compiled recipe (Layer 3) |
| `list_recipes` | Browse available recipes |
| `get_recipe` | Get recipe details and step definitions |
| `check_credentials` | See what you can call right now |
| `credential_ceremony` | Step-by-step guide to get provider credentials |
| `get_receipt` | Retrieve HMAC-signed execution receipt with chain hash |

## Financial tools (auth required, 5 tools)

| Tool | What it does |
|------|-------------|
| `budget` | Set spending limits |
| `spend` | Track spending |
| `check_balance` | View credits |
| `get_payment_url` | Get Stripe top-up link |
| `get_ledger` | Transaction history |

## Operations tools (auth required, 2 tools)

| Tool | What it does |
|------|-------------|
| `routing` | Choose routing strategy (cheapest, fastest, highest quality, balanced) |
| `usage_telemetry` | Report execution telemetry for L2 learning |

## 21 MCP tools

**Discovery (free):** `find_services`, `get_score`, `get_alternatives`, `get_failure_modes`, `discover_capabilities`, `resolve_capability`

**Execution (auth):** `execute_capability`, `estimate_capability`, `recipe_execute`, `list_recipes`, `get_recipe`, `check_credentials`, `credential_ceremony`, `get_receipt`

**Financial (auth):** `budget`, `spend`, `check_balance`, `get_payment_url`, `get_ledger`

**Operations (auth):** `routing`, `usage_telemetry`

## Common workflows

### 1) Discover tools (no auth)

> "I need an email provider for agents."

- `find_services` → search the landscape
- `get_score` → inspect a specific provider
- `get_failure_modes` → see where it breaks in practice

### 2) Route a capability (no auth)

> "I need `email.send`. What should I use?"

- `discover_capabilities` → find the capability ID
- `resolve_capability` → get ranked providers with health data

### 3) Execute (auth required)

> "Send the email with the cheapest provider above my quality floor."

- `estimate_capability` → preview cost
- `execute_capability` → perform the action
- `get_receipt` → verify the HMAC-signed execution record

### 4) Run a recipe (auth required)

> "Enrich this contact, find their company, and draft an intro email."

- `list_recipes` → browse available workflows
- `recipe_execute` → run the compiled recipe
- Each step is content-firewalled, budget-enforced, and produces a receipt

## x402 micropayments

No account needed — pay per call with USDC on Base:

```json
{
  "env": {
    "RHUMB_X402_WALLET_ADDRESS": "0x...",
    "RHUMB_X402_PRIVATE_KEY": "0x..."
  }
}
```

## Local development

```bash
cd packages/mcp
npm ci
npm run dev
```

## Test and build

```bash
npm test          # 84+ tests
npm run type-check
npm run build
```

## Related

- API: `https://api.rhumb.dev/v1` (v1 compat) / `https://api.rhumb.dev/v2` (Resolve v2)
- npm: https://www.npmjs.com/package/rhumb-mcp
- MCP Registry: https://registry.modelcontextprotocol.io (search "rhumb")
- GitHub: https://github.com/supertrained/rhumb

## License

MIT

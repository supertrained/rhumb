# Rhumb MCP Server

**Agent-native tool intelligence for the Model Context Protocol.**

Three execution layers: raw provider access (Layer 1), intelligent routing (Layer 2), and deterministic composed recipes (Layer 3, beta with a truthful public catalog). Every provider rated with the AN Score. Every execution produces a chain-hashed receipt.

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
- *"Check whether any Rhumb recipes are published yet"*

## Current launchable scope

Rhumb is strongest today for **research, extraction, generation, and narrow enrichment**.

Treat it as capability infrastructure first, not as a general business-agent automation layer yet. Layer 2 is the real production surface today; Layer 3 is still beta with an intentionally sparse public catalog.

Discovery breadth is wider than current execution breadth: Rhumb scores **1,038 services** and exposes **415 capability definitions**, but current governed execution is concentrated in **16 callable providers**.

## Resolve mental model

- **Service** = vendor Rhumb evaluates and compares
- **Capability** = executable action your MCP client can route and execute
- **Recipe** = deterministic multi-step workflow on top of capabilities (beta, sparse public catalog)
- **Layer 2 is the default path** — discover → resolve → estimate → execute
- **Default auth for repeat traffic** = governed API key or wallet-prefund on `X-Rhumb-Key`
- **Bring BYOK or Agent Vault** only when provider control is the point
- **Use x402** only when zero-signup per-call payment is the point

Canonical onboarding map: <https://rhumb.dev/docs#resolve-mental-model>

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
- New tools for recipe-catalog inspection, receipts, and telemetry
- Update: `npx rhumb-mcp@2` (or `npx rhumb-mcp@latest`)

<!-- GENERATED:MCP_README_TOOL_SURFACE_START -->
## Discovery tools (no auth, 6 tools)

| Tool | What it does |
|------|-------------|
| `find_services` | Search indexed Services by what you need them to do |
| `get_score` | Get the full AN Score breakdown for a Service: execution quality, access readiness, autonomy level, tier label, and freshness |
| `get_alternatives` | Find alternative Services, ranked by AN Score |
| `get_failure_modes` | Get known failure patterns, impact severity, and workarounds for a service |
| `discover_capabilities` | Browse Capabilities by domain or search text |
| `resolve_capability` | Given a Capability ID, and optionally a credential mode, returns ranked providers with health status, cost per call, auth methods, endpoint patterns, execute guidance, and machine-readable recovery fields like recovery_hint.resolve_url, recovery_hint.credential_modes_url, and, when applicable, recovery_hint.alternate_execute_hint or recovery_hint.setup_handoff, plus typo recovery when the capability ID is wrong |

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
| `execute_capability` | Call a Capability through Rhumb Resolve |
| `estimate_capability` | Estimate the active execution rail, cost, and health before a Capability call; anonymous direct system-of-record paths also preserve machine-readable execute_readiness handoffs |
| `credential_ceremony` | Get step-by-step instructions to obtain API credentials for a Service |
| `check_credentials` | Inspect live credential-mode readiness, globally or for a specific Capability |
| `rhumb_list_recipes` | List the current published Rhumb Layer 3 recipe catalog |
| `rhumb_get_recipe` | Get the full published definition for a Rhumb recipe, including input/output schemas and step topology |
| `rhumb_recipe_execute` | Execute a published Rhumb Layer 3 recipe once one is live in the public catalog |
| `get_receipt` | Retrieve an execution receipt by ID |

## Financial tools (auth required, 5 tools)

| Tool | What it does |
|------|-------------|
| `budget` | Check or set your call spending limit |
| `spend` | Get your spending breakdown for a billing period: total USD spent, call count, average cost per call, broken down by Capability and by provider |
| `check_balance` | Check your current Rhumb credit balance in USD |
| `get_payment_url` | Get a checkout URL to add credits to your Rhumb balance |
| `get_ledger` | Get your billing history: charges (debits), top-ups (credits), and auto-reload events |

## Operations tools (auth required, 2 tools)

| Tool | What it does |
|------|-------------|
| `routing` | Get or set how Rhumb auto-selects providers when you don't specify one in execute_capability |
| `usage_telemetry` | Get your execution analytics — calls, latency, errors, costs, and provider health for your Rhumb usage |

## 21 MCP tools

**Discovery (free):** `find_services`, `get_score`, `get_alternatives`, `get_failure_modes`, `discover_capabilities`, `resolve_capability`

**Execution (auth):** `execute_capability`, `estimate_capability`, `credential_ceremony`, `check_credentials`, `rhumb_list_recipes`, `rhumb_get_recipe`, `rhumb_recipe_execute`, `get_receipt`

**Financial (auth):** `budget`, `spend`, `check_balance`, `get_payment_url`, `get_ledger`

**Operations (auth):** `routing`, `usage_telemetry`

> Discovery spans 1,038 scored services, but current governed execution spans 16 callable providers.

> Best current fit: research, extraction, generation, and narrow enrichment. Treat general business-agent automation as future scope, not the current launch promise.
<!-- GENERATED:MCP_README_TOOL_SURFACE_END -->

## Common workflows

### 1) Discover tools (no auth)

> "I need an email provider for agents."

- `find_services` → search the landscape
- `get_score` → inspect a specific provider
- `get_failure_modes` → see where it breaks in practice

### 2) Route a capability (no auth)

> "I need `email.send`. What should I use?"

- `discover_capabilities` → find the capability ID
- `resolve_capability` → get ranked providers, optional credential-mode filtering, machine-readable recovery fields like `recovery_hint.resolve_url`, `recovery_hint.credential_modes_url`, and, when applicable, `recovery_hint.alternate_execute_hint` or `recovery_hint.setup_handoff`, or search suggestions when the capability ID is wrong

### 3) Check readiness (auth required)

> "Can I call `deployment.list` right now, and on which rail?"

- `check_credentials` → call without params for account-wide configured BYOK/direct-bundle readiness, or pass a capability to inspect provider-level mode status and ceremony availability

### 4) Execute (auth required)

> "Send the email with the cheapest provider above my quality floor."

- `estimate_capability` → check the active execution rail, health, and cost before execution
- `execute_capability` → perform the action
- `get_receipt` → verify the HMAC-signed execution record

### 5) Check recipe availability / run a recipe (auth required)

> "Is there already a published Rhumb workflow for this?"

- `rhumb_list_recipes` → check what is actually live in the public catalog
- `rhumb_get_recipe` → inspect a recipe only after it appears there
- `rhumb_recipe_execute` → run the compiled recipe once it is published
- Public note: the Layer 3 catalog is currently sparse/empty, so most real work should use Layer 2 capabilities today

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

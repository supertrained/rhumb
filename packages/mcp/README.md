# Rhumb MCP Server

**Agent-native tool intelligence for the Model Context Protocol.**

Discover, compare, route, and execute across 600+ scored API services. Every tool rated for AI agent use with the AN Score.

- Website: https://rhumb.dev
- Docs: https://rhumb.dev/blog/getting-started-mcp
- Pricing: https://rhumb.dev/pricing
- Repo: https://github.com/supertrained/rhumb

## Zero-config quickstart

**No API key needed for discovery.** Install and start finding tools immediately:

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

That's it. Ask your agent:
- *"Find me the best email API for agents"*
- *"What's the AN Score for Stripe?"*
- *"Compare Resend vs SendGrid vs Postmark"*
- *"What are Twilio's known failure modes?"*

All of these work **without an account or API key**.

## What works without auth (6 tools)

| Tool | What it does |
|------|-------------|
| `find_services` | Search 600+ services by what you need |
| `get_score` | Full AN Score breakdown for any service |
| `get_alternatives` | Find alternatives ranked by score |
| `get_failure_modes` | Known failure patterns + workarounds |
| `discover_capabilities` | Browse capabilities by domain (`email.send`, `payment.charge`) |
| `resolve_capability` | Get ranked providers with health, cost, and routing data |

## What requires auth (10 tools)

For execution, billing, and credential management, add your API key:

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

Get a key at https://rhumb.dev/auth/login (GitHub or Google OAuth, 30 seconds).

| Tool | What it does |
|------|-------------|
| `execute_capability` | Call a capability through Rhumb Resolve |
| `estimate_capability` | Get cost before executing (no charge) |
| `check_credentials` | See what you can call right now |
| `credential_ceremony` | Step-by-step guide to get provider credentials |
| `budget` / `spend` | Set and track spending limits |
| `check_balance` / `get_ledger` | View credits and transaction history |
| `get_payment_url` | Get Stripe top-up link |
| `routing` | Choose strategy: cheapest, fastest, highest quality |

**Alternative: x402 micropayments.** No account needed — pay per call with USDC on Base. Pass `x_payment` instead of an API key.

## Common workflows

### 1) Discover tools (no auth needed)

> "I need an email provider for agents."

- `find_services` → search the landscape
- `get_score` → inspect a specific provider
- `get_failure_modes` → see where it breaks in practice

### 2) Route a capability (no auth needed)

> "I need `email.send`. What should I use?"

- `discover_capabilities` → find the capability ID
- `resolve_capability` → get ranked providers with health data
- `estimate_capability` → preview cost (requires auth)

### 3) Execute (auth required)

> "Send the email with the cheapest provider above my quality floor."

- `execute_capability` → actually perform the action
- `budget` / `spend` / `check_balance` → control and audit usage

## 16 MCP tools

- `find_services` — search services by need
- `get_score` — full AN Score breakdown
- `get_alternatives` — ranked alternatives
- `get_failure_modes` — failure patterns + workarounds
- `discover_capabilities` — browse by domain
- `resolve_capability` — ranked providers with routing data
- `execute_capability` — call through Rhumb Resolve
- `estimate_capability` — cost preview (no charge)
- `credential_ceremony` — provider credential guides
- `check_credentials` — what modes are available
- `budget` — set spending limits
- `spend` — track spending
- `routing` — choose routing strategy
- `check_balance` — view credits
- `get_payment_url` — Stripe top-up link
- `get_ledger` — transaction history

## Local development

```bash
cd packages/mcp
npm ci
npm run dev
```

## Test and build

```bash
npm test          # 78 tests
npm run type-check
npm run build
```

## Related

- API: `https://api.rhumb.dev/v1`
- npm: https://www.npmjs.com/package/rhumb-mcp
- MCP Registry: https://registry.modelcontextprotocol.io (search "rhumb")
- GitHub: https://github.com/supertrained/rhumb

## License

MIT

# Rhumb MCP Server

**Agent-native tool intelligence for the Model Context Protocol.**

Rhumb helps agents discover, compare, route, and execute external tools with visible failure modes, budget controls, and multiple credential paths.

- Website: https://rhumb.dev
- Quickstart: https://rhumb.dev/quickstart
- Pricing: https://rhumb.dev/pricing
- Trust: https://rhumb.dev/trust
- Repo: https://github.com/supertrained/rhumb

## What it gives you

`rhumb-mcp@0.7.0` exposes **16 MCP tools** across discovery, scoring, capability routing, execution, credential management, and billing:

- `find_tools`
- `get_score`
- `get_alternatives`
- `get_failure_modes`
- `discover_capabilities`
- `resolve_capability`
- `execute_capability`
- `estimate_capability`
- `credential_ceremony`
- `check_credentials`
- `budget`
- `spend`
- `routing`
- `check_balance`
- `get_payment_url`
- `get_ledger`

With those tools, an agent can:
- find the best provider for a task
- inspect scores and failure modes before committing
- route to the cheapest acceptable provider
- estimate cost before execution
- execute through Rhumb with API key, x402 payment, or BYO upstream credentials
- monitor credits, payments, and spend

## Install

Run directly with `npx`:

```bash
npx rhumb-mcp@0.7.0
```

## Execution paths

Rhumb currently supports three practical execution paths:

1. **API key** — sign up, get a Rhumb key, send `X-Rhumb-Key`
2. **x402 / USDC** — no signup, pay per call, send `X-Payment`
3. **BYO upstream key** — pass your own upstream credentials when the capability supports it

## Claude Desktop

Add Rhumb to your Claude Desktop MCP config:

```json
{
  "mcpServers": {
    "rhumb": {
      "command": "npx",
      "args": ["-y", "rhumb-mcp@0.7.0"]
    }
  }
}
```

Then restart Claude Desktop.

For broader setup guidance, use:
- Quickstart: https://rhumb.dev/quickstart
- Repository docs: https://github.com/supertrained/rhumb/tree/main/packages/mcp/docs

## Common workflows

### 1) Discover tools

> “I need an email provider for agents.”

- `find_tools` to search the landscape
- `get_score` to inspect a specific provider
- `get_failure_modes` to see where it breaks in practice

### 2) Route a capability

> “I need `email.send`. What should I use?”

- `resolve_capability` to get ranked providers
- `estimate_capability` to preview cost
- `routing` to choose a strategy (`cheapest`, `fastest`, `highest_quality`, `balanced`)

### 3) Execute

> “Send the email with the cheapest provider above my quality floor.”

- `execute_capability` to actually perform the action
- `budget` / `spend` / `check_balance` / `get_ledger` to control and audit usage

## Local development

```bash
cd packages/mcp
npm ci
npm run dev
```

## Test and build

```bash
npm test
npm run type-check
npm run build
```

## Package structure

- `src/index.ts` — stdio entry point
- `src/server.ts` — MCP server + tool registration
- `src/api-client.ts` — Rhumb API client
- `src/tools/` — tool handlers
- `src/types.ts` — tool schemas and types

## Related surfaces

- API base: `https://api.rhumb.dev/v1`
- npm package: https://www.npmjs.com/package/rhumb-mcp
- Product repo: https://github.com/supertrained/rhumb

## License

MIT

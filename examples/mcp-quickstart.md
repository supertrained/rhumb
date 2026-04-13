# MCP Quickstart

Use Rhumb through the Model Context Protocol — the fastest path to agent tool discovery and execution.

## Default path

For most agents, the default production path is:

1. discover a **Service** or **Capability**
2. resolve ranked providers, or the next setup step
3. estimate the call
4. execute through Layer 2 with `RHUMB_API_KEY`

Use x402 only when zero-signup per-call payment is the point. For repeat wallet traffic, use wallet-prefund and then execute with `X-Rhumb-Key`.

## Install

```bash
npx rhumb-mcp@latest
```

Zero config. Discovery tools work immediately.

## Add to Claude Desktop

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "rhumb": {
      "command": "npx",
      "args": ["rhumb-mcp@latest"],
      "env": {
        "RHUMB_API_KEY": "your_key_here"
      }
    }
  }
}
```

The API key is optional — discovery tools work without it. Add it to enable execution.

## Add to Cursor

In Cursor settings → MCP Servers → Add:

```json
{
  "rhumb": {
    "command": "npx",
    "args": ["rhumb-mcp@latest"],
    "env": {
      "RHUMB_API_KEY": "your_key_here"
    }
  }
}
```

## What you can do

### Without an API key (free, no signup)
- `find_services` — "Find the best email API for agents"
- `get_score` — "What's Stripe's agent-native score?"
- `get_alternatives` — "What are alternatives to SendGrid?"
- `get_failure_modes` — "What breaks when agents use HubSpot?"
- `discover_capabilities` — "What capabilities exist for payments?"

### With an API key (default production path)
- `resolve_capability` — "Which provider or setup step should I use for email.send, and what if I only want BYOK or Rhumb-managed?"
- `estimate_capability` — "How much will this call cost?"
- `execute_capability` — "Send an email through the best provider"
- `get_receipt` — "Show me the receipt for that execution"
- `usage_telemetry` — "How are my calls performing this week?"
- `budget` / `spend` — "Set a $10/day budget"

### Minimal recommended flow

1. `discover_capabilities` — find the action you want
2. `resolve_capability` — see ranked providers, optional credential-mode filters, and recovery handoffs
3. `estimate_capability` — check cost before paying
4. `execute_capability` — run the action

If you ask for a specific mode such as `byok` or `rhumb_managed` and nothing is execute-ready, `resolve_capability` can still return the next action as machine-readable `alternate_execute_hint` or `setup_handoff` instead of leaving you to rediscover it manually.

## Get an API key

1. Go to [rhumb.dev/auth/login](https://rhumb.dev/auth/login)
2. Sign in with GitHub or Google
3. Copy your API key from the dashboard

## Example conversation

> **You:** Find me the best API for sending transactional emails from an AI agent.
>
> **Agent (using find_services):** Found 8 email services. Top 3 by AN Score:
> - Resend: 7.8 (L3 Ready) — cleanest API, best agent ergonomics
> - Postmark: 6.8 (L3 Ready) — reliable delivery, some signup friction  
> - SendGrid: 5.5 (L2 Developing) — powerful but complex auth model
>
> **You:** What are Resend's failure modes?
>
> **Agent (using get_failure_modes):** 3 known failure modes for Resend:
> - Domain verification required before sending (blocks cold start)
> - Rate limit headers not always present
> - Webhook signatures use asymmetric keys (unusual pattern)
>
> **You:** Ok, send a test email through Resend.
>
> **Agent (using execute_capability):** Executing email.send via Resend...
> - Cost estimate: $0.001
> - Status: 200 OK
> - Message ID: msg_abc123

## Notes

- Discovery works with no key.
- Execution generally means `RHUMB_API_KEY`.
- Use x402 through the REST API when zero-signup per-call payment matters.
- Use wallet-prefund when the same wallet needs repeat traffic.

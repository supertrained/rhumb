# MCP Quickstart

Use Rhumb through the Model Context Protocol — the fastest path to agent tool discovery and execution.

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
- `an_score` — "What's Stripe's agent-native score?"
- `get_alternatives` — "What are alternatives to SendGrid?"
- `get_failure_modes` — "What breaks when agents use HubSpot?"
- `discover_capabilities` — "What capabilities exist for payments?"

### With an API key
- `resolve_capability` — "Which provider should I use for email.send?"
- `execute_capability` — "Send an email through the best provider"
- `estimate_capability` — "How much will this call cost?"
- `budget` / `spend` — "Set a $10/day budget"

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

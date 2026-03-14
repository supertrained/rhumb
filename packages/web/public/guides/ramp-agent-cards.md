# Ramp Agent Cards — Agent-Native Service Guide

> **AN Score:** Pending · **Tier:** Pending · **Category:** Agent Payment Infrastructure

---

## 1. Synopsis

Ramp Agent Cards are programmable virtual Visa cards designed specifically for AI agents. Backed by Ramp ($13B+ fintech), they let agents autonomously issue, manage, and spend on corporate cards with built-in governance: spend limits, merchant restrictions, category controls, and full audit trails. Available via REST API, MCP, and CLI. Ramp is the first major corporate card provider to ship agent-native infrastructure, launching March 11, 2026. Sandbox available for free testing; production requires Ramp business account and PCI approval for full card details.

---

## 2. Connection Methods

### REST API
- **Base URL:** `https://api.ramp.com/developer/v1` (production), `https://demo-api.ramp.com/developer/v1` (sandbox)
- **Auth:** OAuth 2.0 Client Credentials — POST `/developer/v1/token` with Client ID and Client Secret
- **Scopes:** `cards:read_vault`, `limits:write`, `users:read` (opt)
- **Rate Limits:** 200 requests per 10-second rolling window per source IP. 429 on exceed; 504 after 60s timeout.
- **Docs:** https://docs.ramp.com/developer-api/v1

### MCP
- **Ramp MCP:** Official MCP integration for end-users — connects AI assistants to Ramp for querying data and performing actions like issuing cards via natural language.
- **Developer MCP:** AI-powered tool for developers — `search_documentation`, `get_endpoint_schema`. No Ramp account needed.
- **Docs:** https://docs.ramp.com/developer-api/v1/mcp

### CLI
- Agent Cards can be managed via Ramp's CLI tools (integrated with MCP)
- Works with any agent framework

### Webhooks
- **Events:** `transactions.cleared`, `cards.created`, etc.
- **Deferred tasks:** Async operations return `task_id` for polling
- Standard webhook retry policy

### Auth Flows
- **OAuth 2.0 Client Credentials:** Primary flow for agents. Create app at developer.ramp.com, get Client ID/Secret
- **PCI Approval:** Required for production access to full card details (PAN/CVV). Sandbox is unrestricted.

---

## 3. Key Primitives

| Primitive | Endpoint | Description |
|-----------|----------|-------------|
| `card.create` | `POST /developer/v1/vault/cards` | Issue a new virtual card with spending restrictions |
| `card.terminate` | `POST /developer/v1/limits/{id}/deferred/termination` | Terminate a card (async, irreversible) |
| `card.list` | `GET /developer/v1/vault/cards` | List all virtual cards |
| `transaction.list` | `GET /developer/v1/transactions` | Query transaction history |
| `limit.update` | `PATCH /developer/v1/limits/{id}` | Update spending limits |
| `user.list` | `GET /developer/v1/users` | List users (for user_id on card creation) |

---

## 4. Setup Guide

### Step 1: Get Developer Access
- **Ramp customer:** Navigate to Company → Developer → Create New App
- **Not a customer:** Apply via https://ramp.com/technology-partnerships

### Step 2: Configure OAuth
```bash
# .env
RAMP_CLIENT_ID=your_client_id
RAMP_CLIENT_SECRET=your_client_secret
```

### Step 3: Get Access Token
```bash
curl -X POST https://demo-api.ramp.com/developer/v1/token \
  -d "grant_type=client_credentials" \
  -d "client_id=$RAMP_CLIENT_ID" \
  -d "client_secret=$RAMP_CLIENT_SECRET" \
  -d "scope=cards:read_vault limits:write"
```

### Step 4: Issue a Card
```bash
curl -X POST https://demo-api.ramp.com/developer/v1/vault/cards \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user_123",
    "display_name": "AI Agent SaaS Budget",
    "spending_restrictions": {
      "limit": {"amount": 50000, "currency_code": "USD"},
      "allowed_categories": [5734, 5817],
      "interval": "MONTHLY"
    }
  }'
```

---

## 5. Common Failure Modes

### PCI Gate for Production
- **What:** Full card details (PAN, CVV, expiration) require PCI DSS approval in production
- **Impact:** Agents can create and manage cards but cannot read full card numbers without PCI compliance
- **Mitigation:** Use sandbox for testing; submit PCI ticket for production

### Business Account Required
- **What:** Production API requires active Ramp business account with admin access
- **Impact:** Cannot programmatically create a Ramp account — must be human-approved
- **Mitigation:** Sandbox available immediately for development and testing

### Card Termination is Irreversible
- **What:** `POST /limits/{id}/deferred/termination` is async AND irreversible
- **Impact:** Agents must implement confirmation logic; no undo
- **Mitigation:** Build approval workflow before termination; use sandbox for testing

### Category Code Complexity
- **What:** Merchant category restrictions use MCC codes (numeric), not human-readable categories
- **Impact:** Agents must maintain MCC code mappings for proper spending controls
- **Mitigation:** Use Developer MCP to query category codes; maintain lookup table

### IP-Based Rate Limiting
- **What:** 200 requests/10s per IP, not per API key
- **Impact:** Multiple agents sharing an IP will share the rate limit
- **Mitigation:** Distribute agents across IPs; implement backoff on 429

---

## 6. Competitive Context

Ramp Agent Cards compete with:
- **Crossmint:** Agent card payments (crypto-native, different compliance model)
- **Stripe Issuing:** Virtual cards via API (not explicitly agent-native)
- **Brex:** Virtual cards for startups (no dedicated agent product yet)

Ramp's differentiation: first major corporate card provider with explicit agent-native framing, MCP integration, and dual-surface design (human dashboard + agent API).

---

## 7. Rhumb Assessment Notes

- **Agent-native design:** Purpose-built for AI agents, not retrofitted from human card management
- **Governance-first:** Spend limits, merchant controls, and audit trails are first-class primitives
- **MCP integration:** Natural composability with other MCP-enabled tools
- **Key limitation:** PCI gate creates a two-tier access model — agents can manage cards but may not see full card numbers without compliance review
- **Market signal:** Validates that agent payment infrastructure is an emerging category

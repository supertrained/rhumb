# Rhumb

**Agent-native tool intelligence.** Discover, score, and execute APIs — with cost-aware routing, budget enforcement, and three credential modes. Built for autonomous agents, not humans browsing docs.

🌐 [rhumb.dev](https://rhumb.dev) · 📊 [Leaderboard](https://rhumb.dev/leaderboard) · 📖 [Methodology](https://rhumb.dev/methodology) · 🔌 [MCP Server](https://www.npmjs.com/package/rhumb-mcp) · 🔑 [Trust](https://rhumb.dev/trust)

## What is Rhumb?

Rhumb is the infrastructure layer agents use to **discover, access, and trust** external tools.

- **212 scored services** across 38 categories, evaluated on 20 dimensions
- **103 capabilities** across 30 domains (email.send, project.create_issue, ai.generate_text, spreadsheet.read, ...)
- **3 credential modes** — bring your own token, zero-config managed, or self-provisioned via ceremony guides
- **Cost-optimal routing** — cheapest provider that meets your quality floor
- **Budget enforcement** — pre-execution checks, not surprise bills

## MCP Server

```bash
npx rhumb-mcp@0.5.0
```

**13 tools:**

| Tool | What it does |
|------|-------------|
| `find_tools` | Search services by category or capability |
| `get_score` | AN Score and dimension breakdown for a service |
| `get_alternatives` | Find alternatives ranked by score |
| `get_failure_modes` | Known failure modes and workarounds |
| `discover_capabilities` | Browse capabilities by domain |
| `resolve_capability` | Ranked providers with health + cost for a capability |
| `execute_capability` | Execute through Rhumb — auto-selects provider, injects auth |
| `estimate_capability` | Cost estimate + budget check without executing |
| `credential_ceremony` | Step-by-step guide to get API credentials for a service |
| `check_credentials` | Your credential status across all three modes |
| `budget` | Check or set your execution budget |
| `spend` | Spend breakdown by capability and provider |
| `routing` | Get or set your routing strategy |

### Quick Example

```
# "I need to send an email. What should I use?"
resolve_capability("email.send")
→ 8 providers ranked: Resend (8.3), SendGrid (7.5), Postmark (7.2), ...

# "Use the cheapest one that's good enough"
routing(set, strategy="cheapest", quality_floor=7.0)

# "Send it — zero config, Rhumb handles credentials"
execute_capability("email.send", credential_mode="rhumb_managed", body={
  from: "agent@example.com", to: "user@example.com",
  subject: "Hello", html: "<p>Sent via Rhumb</p>"
})
→ { provider_used: "resend", upstream_status: 200, budget_remaining_usd: 49.99 }
```

## Three Credential Modes

| Mode | How it works | When to use |
|------|-------------|-------------|
| **BYO Token** | You provide your own API key | Full control, existing credentials |
| **Rhumb Managed** | Zero-config — Rhumb provides credentials | Quick start, managed capabilities |
| **Agent Vault** | Self-provision via ceremony guide, pass per-request | Your own key, Rhumb never stores it |

## AN Score

The Agent-Native Score rates services from 0–10 across two axes:

| Axis | Weight | What it measures |
|------|--------|-----------------|
| **Execution** | 70% | API reliability, error ergonomics, schema stability, latency, idempotency, autonomy |
| **Access Readiness** | 30% | Signup friction, credential management, rate limit transparency, docs quality, sandbox availability |

**Tiers:**
- **L4 Native** (8.0–10.0) — Built for agents
- **L3 Ready** (6.0–7.9) — Works reliably with minor friction
- **L2 Developing** (4.0–5.9) — Usable with workarounds
- **L1 Emerging** (0.0–3.9) — Significant barriers to agent use

Full methodology: [rhumb.dev/methodology](https://rhumb.dev/methodology)

## REST API

Base URL: `https://rhumb-api-production-f173.up.railway.app/v1`

| Endpoint | Description |
|----------|-------------|
| `GET /capabilities` | Browse capability registry |
| `GET /capabilities/{id}/resolve` | Ranked providers for a capability |
| `POST /capabilities/{id}/execute` | Execute a capability |
| `GET /capabilities/{id}/execute/estimate` | Cost estimate |
| `GET /capabilities/rhumb-managed` | Zero-config managed capabilities |
| `GET /services/ceremonies` | All credential ceremony guides |
| `GET /services/{slug}/ceremony` | Ceremony steps for a specific service |
| `GET/PUT /agent/budget` | Budget management |
| `GET/PUT /agent/routing-strategy` | Routing strategy |
| `GET /agent/spend` | Spend breakdown |
| `GET /services/{slug}` | Service details + score |
| `GET /search?q=...` | Service search |

## Project Structure

```
rhumb/
├── packages/
│   ├── web/      # Astro 6.0 frontend (rhumb.dev)
│   ├── mcp/      # MCP server (npx rhumb-mcp)
│   ├── api/      # FastAPI on Railway (Supabase REST)
│   ├── cli/      # CLI tools
│   └── shared/   # Shared types and constants
├── scripts/      # Scoring and verification scripts
└── artifacts/    # Dataset and score artifacts
```

## Development

**Node:** use Node 24 for the Astro site and Vercel-aligned local builds (`nvm use` from the repo root reads `.nvmrc`).

```bash
# API
cd packages/api && pip install -r requirements.txt && uvicorn app:app --reload

# MCP
cd packages/mcp && npm ci && npm run dev

# Web
cd packages/web && npm ci && npm run dev

# Tests
cd packages/api && python -m pytest        # 80+ API tests
cd packages/mcp && npm test                 # 66 MCP tests
```

## Score Disputes

Every score is disputable. If you believe a score is inaccurate:

1. **GitHub Issue:** [Open an issue](https://github.com/supertrained/rhumb/issues/new) with evidence
2. **Email:** [providers@supertrained.ai](mailto:providers@supertrained.ai)

All disputes are reviewed and outcomes are public.

## Links

- **Website:** [rhumb.dev](https://rhumb.dev)
- **About:** [rhumb.dev/about](https://rhumb.dev/about)
- **Trust:** [rhumb.dev/trust](https://rhumb.dev/trust)
- **Blog:** [rhumb.dev/blog](https://rhumb.dev/blog)
- **Twitter:** [@pedrorhumb](https://x.com/pedrorhumb)

## License

[MIT](LICENSE)

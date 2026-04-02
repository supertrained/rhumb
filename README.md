# Rhumb

[![npm version](https://img.shields.io/npm/v/rhumb-mcp)](https://www.npmjs.com/package/rhumb-mcp)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![MCP Registry](https://img.shields.io/badge/MCP-Registry-green)](https://registry.modelcontextprotocol.io)

**Agent-native tool intelligence.** Discover, evaluate, and execute external tools — with trust scores, failure modes, cost-aware routing, and managed credentials.

🌐 [rhumb.dev](https://rhumb.dev) · ⚡ [Quickstart](https://rhumb.dev/quickstart) · 💵 [Pricing](https://rhumb.dev/pricing) · 📊 [Leaderboard](https://rhumb.dev/leaderboard) · 📖 [Methodology](https://rhumb.dev/methodology) · 🔑 [Trust](https://rhumb.dev/trust)

> **For agents:** See [`llms.txt`](llms.txt) for machine-readable documentation and [`agent-capabilities.json`](agent-capabilities.json) for structured capability metadata.

---

## Start in 30 seconds

### MCP (recommended)

```bash
npx rhumb-mcp@latest
```

Zero config. Discovery tools work immediately — no signup, no API key.

For execution, pass your Rhumb API key:

```bash
RHUMB_API_KEY=your_key npx rhumb-mcp@latest
```

[Get an API key →](https://rhumb.dev/auth/login)

### API (read-only, no auth)

```bash
curl "https://api.rhumb.dev/v1/services/stripe/score"
```

All read endpoints are public.

---

## What Rhumb does

Agents need external tools. Choosing the right one is hard — not because of feature lists, but because of:

- auth and signup friction
- provisioning reality vs. marketing claims
- schema instability
- failure recovery when no human is watching
- hidden costs and rate limits

Rhumb makes those constraints visible before you commit.

### Rhumb Index — Discover & Evaluate

**1,038 scored services** across 50+ domains. Each gets an [AN Score](https://rhumb.dev/methodology) (0–10) measuring execution quality, access readiness, and agent autonomy support.

- `find_services` — search by capability, domain, or name
- `get_score` — full score breakdown with dimension-level detail
- `get_alternatives` — ranked alternatives for any service
- `get_failure_modes` — known failure patterns before you integrate

### Rhumb Resolve — Execute

**415 capabilities** across 16 callable providers. Cost-aware routing picks the best provider for each call.

- `execute_capability` — call a capability through Resolve with managed auth
- `resolve_capability` — see ranked providers before executing
- `estimate_capability` — get cost estimate before committing
- Budget enforcement, credential management, and execution telemetry included

### Three credential modes

| Mode | How it works |
|------|-------------|
| **BYO** | Bring your own API key — Rhumb routes, you authenticate |
| **Rhumb-managed** | Rhumb holds the credential — zero setup for the agent |
| **Agent Vault** | Your key, encrypted and stored — Rhumb injects at call time |

### Payment paths

- **API key** — sign up, get a key, prepaid credits
- **x402 / USDC** — no signup, pay per call on-chain

---

## MCP tools

`rhumb-mcp` exposes **21 tools**:

**Discovery**
- `find_services` — search services
- `get_score` — score breakdown
- `get_alternatives` — ranked alternatives
- `get_failure_modes` — failure patterns
- `discover_capabilities` — browse capability registry
- `resolve_capability` — ranked providers for a capability

**Execution**
- `execute_capability` — execute through Resolve
- `estimate_capability` — cost estimate before execution
- `rhumb_list_recipes` — check the current published Layer 3 catalog
- `rhumb_get_recipe` — inspect a recipe only after it appears in that catalog
- `rhumb_recipe_execute` — execute a published Layer 3 recipe once one is live
- `credential_ceremony` — set up credentials
- `check_credentials` — verify credential status
- `get_receipt` — retrieve an HMAC-signed execution receipt

**Billing**
- `budget` — set spend limits
- `spend` — check current spend
- `check_balance` — prepaid balance
- `get_payment_url` — top-up link
- `get_ledger` — transaction history

**Operations**
- `routing` — configure routing strategy
- `usage_telemetry` — your usage analytics

> Note: Layer 3 recipe tooling is live, but the public catalog can still be empty. Use `rhumb_list_recipes` or visit `/recipes` before assuming a workflow exists.

---

## API

Base URL: `https://api.rhumb.dev/v1`

| Endpoint | Auth | Purpose |
|----------|------|---------|
| `GET /services/{slug}/score` | No | Score breakdown |
| `GET /services/{slug}` | No | Service profile + metadata |
| `GET /services/{slug}/failures` | No | Known failure modes |
| `GET /search?q=...` | No | Search services |
| `GET /leaderboard/{category}` | No | Category rankings |
| `GET /capabilities` | No | Capability registry |
| `GET /capabilities/{id}/resolve` | No | Ranked providers |
| `POST /capabilities/{id}/execute` | Yes | Execute a capability |
| `GET /capabilities/{id}/execute/estimate` | Yes | Cost estimate |
| `GET /telemetry/provider-health` | No | Provider health status |
| `GET /telemetry/usage` | Yes | Your usage analytics |
| `GET /pricing` | No | Machine-readable pricing |

---

## Examples

See [`examples/`](examples/) for runnable scripts:

| Example | What it shows | Auth needed? |
|---------|--------------|-------------|
| [discover-and-evaluate.py](examples/discover-and-evaluate.py) | Search → Score → Failure modes | No |
| [resolve-and-execute.py](examples/resolve-and-execute.py) | Resolve → Estimate → Execute | Yes |
| [budget-aware-routing.py](examples/budget-aware-routing.py) | Budget + cost-optimal routing | Yes |
| [dogfood-telemetry-loop.py](examples/dogfood-telemetry-loop.py) | Repeatable Resolve → telemetry verification loop | Yes |
| [mcp-quickstart.md](examples/mcp-quickstart.md) | MCP setup for Claude, Cursor, etc. | Optional |

```bash
# Try discovery right now (no auth needed)
pip install httpx && python examples/discover-and-evaluate.py
```

---

## Docs

- [Agent Accessibility Guidelines](docs/AGENT-ACCESSIBILITY-GUIDELINES.md) — making web interfaces usable by AI agents
- [AN Score Methodology](docs/AN-SCORE-V2-SPEC.md) — scoring dimensions, weights, and rubrics
- [Architecture](docs/ARCHITECTURE.md) — scoring engine design
- [API Reference](docs/API.md) — endpoint details
- [Security Policy](SECURITY.md) — vulnerability reporting and security architecture
- [Runbooks](docs/runbooks/) — operational procedures
- [Dogfood Loop](docs/DOGFOOD-LOOP.md) — repeatable Resolve → telemetry validation harness

---

## Repo structure

```
rhumb/
├── packages/
│   ├── api/         # Python API (Railway)
│   ├── astro-web/   # Public website (Vercel)
│   ├── mcp/         # MCP server (npm)
│   ├── cli/         # CLI tooling
│   └── shared/      # Shared types/constants
├── examples/        # Runnable examples
├── docs/            # Public documentation
├── scripts/         # Scoring + verification
├── artifacts/       # Score datasets
├── llms.txt         # Machine-readable docs for agents
└── agent-capabilities.json  # Structured capability manifest
```

---

## Development

```bash
# API
cd packages/api && pip install -r requirements.txt && uvicorn app:app --reload

# MCP
cd packages/mcp && npm ci && npm run dev

# Web
cd packages/astro-web && npm ci && npm run dev
```

Node 24+ recommended (`.nvmrc` included).

---

## Score disputes

Every score is disputable. If you believe a score is inaccurate:

1. [Open a GitHub issue](https://github.com/supertrained/rhumb/issues/new) with evidence
2. Or email [providers@supertrained.ai](mailto:providers@supertrained.ai)

Negative findings remain visible. Rhumb does not accept payment to change scores.

---

## Links

- **Website:** [rhumb.dev](https://rhumb.dev)
- **npm:** [rhumb-mcp](https://www.npmjs.com/package/rhumb-mcp)
- **MCP Registry:** [Rhumb on MCP Registry](https://registry.modelcontextprotocol.io)
- **X:** [@pedrorhumb](https://x.com/pedrorhumb)

## License

[MIT](LICENSE)

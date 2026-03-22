# Rhumb

**Agent-native tool intelligence.** Discover, score, and execute external tools — with visible failure modes, cost-aware routing, budget enforcement, and agent-native access paths.

Most APIs weren't built for agents. Rhumb helps agents and operators see which tools actually work, how they fail, and how to use them.

🌐 [rhumb.dev](https://rhumb.dev) · ⚡ [Quickstart](https://rhumb.dev/quickstart) · 💵 [Pricing](https://rhumb.dev/pricing) · 📊 [Leaderboard](https://rhumb.dev/leaderboard) · 📖 [Methodology](https://rhumb.dev/methodology) · 🔑 [Trust](https://rhumb.dev/trust) · 🔌 [npm: rhumb-mcp](https://www.npmjs.com/package/rhumb-mcp)

## What is Rhumb?

Rhumb is the infrastructure layer agents use to **discover, access, and trust** external tools.

- **212 scored services**
- **241 capabilities across 50+ domains** (64 executable via managed credentials)
- **20 scored dimensions** across execution quality and access readiness
- **3 credential modes** — BYO, Rhumb-managed, and Agent Vault
- **x402 zero-signup path** for agent-native per-call payment
- **Cost-aware routing + budget enforcement** before execution, not surprise bills

## Start in 30 seconds

### Read-only API call

```bash
curl "https://api.rhumb.dev/v1/services/stripe/score"
```

Read endpoints are public and do not require signup.

### MCP

```bash
npx rhumb-mcp@0.7.0
```

### Execute capabilities

Execution paths today:
- **API key** — sign up, get a key, send `X-Rhumb-Key`
- **x402 / USDC** — no signup, pay per call, send `X-Payment`
- **Bring your own key** — pass your own upstream credentials

## MCP tools

`rhumb-mcp@0.7.0` exposes **16 tools** across discovery, routing, execution, credential management, and billing:

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

## Why it exists

Choosing tools for agents is not the same as choosing tools for human developers.

The hard part is not feature breadth. It's whether a tool can actually survive agent-style use:
- auth and signup friction
- provisioning reality
- schema instability
- hidden support burden
- weak docs or unclear limits
- failure recovery when no human is watching

Rhumb makes those constraints legible before you commit.

## AN Score

The Agent-Native (AN) Score rates services from 0–10 across two axes:

| Axis | Weight | What it measures |
|------|--------|------------------|
| **Execution** | 70% | Reliability, error ergonomics, schema stability, latency, idempotency, autonomy |
| **Access Readiness** | 30% | Signup friction, credential management, rate limits, documentation quality, sandbox availability |

**Tiers**
- **L4 Native** (8.0–10.0) — built for agents
- **L3 Ready** (6.0–7.9) — reliable with minor friction
- **L2 Developing** (4.0–5.9) — usable with workarounds
- **L1 Emerging** (0.0–3.9) — significant barriers to agent use

Full methodology: [rhumb.dev/methodology](https://rhumb.dev/methodology)

## Core API surfaces

Base URL: `https://api.rhumb.dev/v1`

| Endpoint | Purpose |
|----------|---------|
| `GET /services/{slug}/score` | Score breakdown for a service |
| `GET /services/{slug}` | Service profile, alternatives, and metadata |
| `GET /services/{slug}/failures` | Known failure modes |
| `GET /search?q=...` | Search services |
| `GET /leaderboard/{category}` | Browse ranked category pages |
| `GET /capabilities` | Browse capability registry |
| `GET /capabilities/{id}/resolve` | Ranked providers for a capability |
| `POST /capabilities/{id}/execute` | Execute a capability |
| `GET /capabilities/{id}/execute/estimate` | Estimate cost before execution |
| `GET /pricing` | Canonical machine-readable pricing contract |

## Repo structure

```text
rhumb/
├── packages/
│   ├── api/         # Railway-hosted API
│   ├── astro-web/   # Public website (rhumb.dev)
│   ├── mcp/         # MCP server (npx rhumb-mcp)
│   ├── cli/         # CLI tooling
│   └── shared/      # Shared types/constants
├── scripts/         # Scoring + verification scripts
└── artifacts/       # Datasets and score artifacts
```

## Development

**Node:** use Node 24 for the Astro/Vercel-aligned web surface (`nvm use` from repo root reads `.nvmrc`).

```bash
# API
cd packages/api && pip install -r requirements.txt && uvicorn app:app --reload

# MCP
cd packages/mcp && npm ci && npm run dev

# Web
cd packages/astro-web && npm ci && npm run dev
```

## Score disputes

Every score is disputable. If you believe a score is inaccurate:

1. Open a [GitHub issue](https://github.com/supertrained/rhumb/issues/new) with evidence
2. Or email [providers@supertrained.ai](mailto:providers@supertrained.ai)

Negative findings remain visible. If Rhumb ever becomes pay-to-rank, it stops being useful.

## Links

- **Website:** [rhumb.dev](https://rhumb.dev)
- **Quickstart:** [rhumb.dev/quickstart](https://rhumb.dev/quickstart)
- **Pricing:** [rhumb.dev/pricing](https://rhumb.dev/pricing)
- **Trust:** [rhumb.dev/trust](https://rhumb.dev/trust)
- **Blog:** [rhumb.dev/blog](https://rhumb.dev/blog)
- **X / Twitter:** [@pedrorhumb](https://x.com/pedrorhumb)

## License

[MIT](LICENSE)

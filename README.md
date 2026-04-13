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

### Best fit today

Rhumb is strongest today for **research, extraction, generation, and narrow enrichment**.

Treat broader multi-system business automation as future scope, not the current launch promise. Use Layer 2 capabilities for real work now, and treat Layer 3 as beta with an intentionally sparse public catalog.

<!-- GENERATED:README_PRODUCT_SURFACE_START -->
### Rhumb Index — Discover & Evaluate

**1,038 scored services** across 50+ domains. Each gets an [AN Score](https://rhumb.dev/methodology) (0–10) measuring execution quality, access readiness, and agent autonomy support.

- `find_services` — Search indexed Services by what you need them to do
- `get_score` — Get the full AN Score breakdown for a Service: execution quality, access readiness, autonomy level, tier label, and freshness
- `get_alternatives` — Find alternative Services, ranked by AN Score
- `get_failure_modes` — Get known failure patterns, impact severity, and workarounds for a service
- `discover_capabilities` — Browse Capabilities by domain or search text
- `resolve_capability` — Given a Capability ID, returns ranked providers with health status, cost per call, auth methods, endpoint patterns, and fallback chains

> Discovery breadth is wider than current execution coverage. The index is broader than what Rhumb can execute today.

### Rhumb Resolve — Execute

**415 capability definitions** across **16 callable providers today**. Cost-aware routing picks the best provider where execution is actually live.

- `execute_capability` — Call a Capability through Rhumb Resolve
- `resolve_capability` — Given a Capability ID, returns ranked providers with health status, cost per call, auth methods, endpoint patterns, and fallback chains
- `estimate_capability` — Get the cost of a Capability call WITHOUT making the call
- `get_receipt` — Retrieve an execution receipt by ID
- Budget enforcement, credential management, and execution telemetry included

> Best current fit: research, extraction, generation, and narrow enrichment. Treat general business-agent automation and broad multi-system orchestration as future scope, not the current launch promise.
<!-- GENERATED:README_PRODUCT_SURFACE_END -->

### Three credential modes

| Mode | How it works |
|------|-------------|
| **BYOK** | Bring your own API key — Rhumb routes, you authenticate |
| **Rhumb-managed** | Rhumb holds the credential — zero setup for the agent |
| **Agent Vault** | Your key, encrypted and stored — Rhumb injects at call time |

### Payment paths

- **API key** — sign up, get a key, prepaid credits
- **x402 / USDC** — no signup, pay per call on-chain

### Resolve mental model

- **Service** = vendor Rhumb evaluates and compares
- **Capability** = executable action like `email.send`
- **Recipe** = deterministic multi-step workflow on top of capabilities (beta, sparse public catalog)
- **Layer 2 is the default path** — give your agent one key, discover a Service, choose a Capability, estimate, then execute
- **Start with managed superpowers first** — bring BYOK or Agent Vault only when the workflow touches your own systems
- **Default auth for repeat traffic** = governed API key or wallet-prefunded API key
- **Use x402** when zero-signup per-call payment matters more than repeat throughput

Canonical onboarding map: <https://rhumb.dev/docs#resolve-mental-model>

---

## MCP tools

<!-- GENERATED:README_MCP_TOOLS_START -->
`rhumb-mcp` exposes **21 tools**:

**Discovery**
- `find_services` — Search indexed Services by what you need them to do
- `get_score` — Get the full AN Score breakdown for a Service: execution quality, access readiness, autonomy level, tier label, and freshness
- `get_alternatives` — Find alternative Services, ranked by AN Score
- `get_failure_modes` — Get known failure patterns, impact severity, and workarounds for a service
- `discover_capabilities` — Browse Capabilities by domain or search text
- `resolve_capability` — Given a Capability ID, returns ranked providers with health status, cost per call, auth methods, endpoint patterns, and fallback chains

**Execution**
- `execute_capability` — Call a Capability through Rhumb Resolve
- `estimate_capability` — Get the cost of a Capability call WITHOUT making the call
- `credential_ceremony` — Get step-by-step instructions to obtain API credentials for a Service
- `check_credentials` — Check what credential modes are available to you
- `rhumb_list_recipes` — List the current published Rhumb Layer 3 recipe catalog
- `rhumb_get_recipe` — Get the full published definition for a Rhumb recipe, including input/output schemas and step topology
- `rhumb_recipe_execute` — Execute a published Rhumb Layer 3 recipe once one is live in the public catalog
- `get_receipt` — Retrieve an execution receipt by ID

**Billing**
- `budget` — Check or set your call spending limit
- `spend` — Get your spending breakdown for a billing period: total USD spent, call count, average cost per call, broken down by Capability and by provider
- `check_balance` — Check your current Rhumb credit balance in USD
- `get_payment_url` — Get a checkout URL to add credits to your Rhumb balance
- `get_ledger` — Get your billing history: charges (debits), top-ups (credits), and auto-reload events

**Operations**
- `routing` — Get or set how Rhumb auto-selects providers when you don't specify one in execute_capability
- `usage_telemetry` — Get your execution analytics — calls, latency, errors, costs, and provider health for your Rhumb usage

> Discovery spans 1,038 scored services, but current governed execution spans 16 callable providers.

> Note: Layer 3 recipe tooling is live, but the public catalog can still be empty. Use `rhumb_list_recipes` or visit `/recipes` before assuming a workflow exists.

> Best current fit: research, extraction, generation, and narrow enrichment. Treat general business-agent automation as future scope, not the current launch promise.
<!-- GENERATED:README_MCP_TOOLS_END -->

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
| [resolve-and-execute.py](examples/resolve-and-execute.py) | Resolve → recovery handoff → Estimate → Execute | No for resolve, yes for estimate/execute |
| [budget-aware-routing.py](examples/budget-aware-routing.py) | Budget + cost-optimal routing | Yes |
| [dogfood-telemetry-loop.py](examples/dogfood-telemetry-loop.py) | Repeatable Resolve → telemetry verification loop | Yes |
| [mcp-quickstart.md](examples/mcp-quickstart.md) | MCP setup for Claude, Cursor, etc. | Optional |

```bash
# Try discovery right now (no auth needed)
pip install httpx && python examples/discover-and-evaluate.py

# Try the resolve walkthrough right now (no auth needed for resolve)
python examples/resolve-and-execute.py
```

`resolve-and-execute.py` will still show the ranked providers plus any recovery handoff Rhumb already identified. Set `RHUMB_API_KEY` only when you want to continue into estimate and execute.

---

## Docs

- [Agent Accessibility Guidelines](docs/AGENT-ACCESSIBILITY-GUIDELINES.md) — making web interfaces usable by AI agents
- [AN Score Methodology](docs/AN-SCORE-V2-SPEC.md) — scoring dimensions, weights, and rubrics
- [Architecture](docs/ARCHITECTURE.md) — scoring engine design
- [API Reference](docs/API.md) — endpoint details
- [Repo Boundary](docs/REPO-BOUNDARY.md) — what stays public here vs. what lives in the private ops workspace
- [Security Policy](SECURITY.md) — vulnerability reporting and security architecture

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
├── docs/            # Public documentation only
├── scripts/         # Product tooling + verification scripts
├── artifacts/       # Curated public datasets only (raw proof outputs stay local/private)
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

1. Read the public provider guide at [rhumb.dev/providers](https://rhumb.dev/providers)
2. [Open the score-dispute GitHub template](https://github.com/supertrained/rhumb/issues/new?template=score-dispute.md) with evidence
3. Or email [providers@supertrained.ai](mailto:providers@supertrained.ai?subject=Score%20Dispute) for a private path

We target an initial response within 5 business days. Negative findings remain visible. Rhumb does not accept payment to change scores.

---

## Links

- **Website:** [rhumb.dev](https://rhumb.dev)
- **npm:** [rhumb-mcp](https://www.npmjs.com/package/rhumb-mcp)
- **MCP Registry:** [Rhumb on MCP Registry](https://registry.modelcontextprotocol.io)
- **X:** [@pedrorhumb](https://x.com/pedrorhumb)

## License

[MIT](LICENSE)

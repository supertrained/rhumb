# Rhumb

**Agent-native tool discovery and scoring.** Every API rated for AI agent compatibility — error ergonomics, schema stability, access readiness, and 17 more dimensions.

🌐 [rhumb.dev](https://rhumb.dev) · 📊 [Leaderboard](https://rhumb.dev/leaderboard) · 📖 [Methodology](https://rhumb.dev/methodology) · 🔌 [MCP Server](https://www.npmjs.com/package/rhumb-mcp)

## What is Rhumb?

Rhumb scores developer tools on how well they work for **autonomous AI agents** — not humans browsing docs, but machines making API calls with no one in the loop.

Existing directories measure UI quality and community size. Rhumb measures what agents need: machine-readable errors, idempotent retries, predictable schemas, and programmatic access.

**Current coverage:** 54 scored services across 11 categories, evaluated on 20 dimensions.

## MCP Server

Query Rhumb scores from any MCP-compatible agent:

```bash
npx rhumb-mcp
```

**Tools available:**
- `find_tools` — Search services by category or capability
- `get_score` — Get the AN Score and breakdown for a service
- `get_alternatives` — Find alternatives to a service
- `get_failure_modes` — Get known failure modes and workarounds

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

## Project Structure

```
rhumb/
├── packages/
│   ├── web/      # Next.js 15 frontend (rhumb.dev)
│   ├── mcp/      # MCP server (npx rhumb-mcp)
│   ├── api/      # Railway API (Supabase REST proxy)
│   ├── cli/      # CLI tools
│   └── shared/   # Shared types and constants
├── scripts/      # Scoring and verification scripts
└── artifacts/    # Dataset and score artifacts
```

## Development

```bash
# Install dependencies
cd packages/web && npm ci

# Run development server
npm run dev

# Run tests
npm test

# Production build
npm run build
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

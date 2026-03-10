import { getServices, getCategories } from "../../lib/api";

export const revalidate = 3600; // Cache for 1 hour

export async function GET() {
  const [services, categories] = await Promise.all([
    getServices(),
    getCategories(),
  ]);

  const categoryList = categories
    .map((c) => `- /leaderboard/${c.slug} (${c.serviceCount} services)`)
    .join("\n");

  const serviceList = services
    .map((s) => `- /service/${s.slug} — ${s.description ?? s.name} [${s.category}]`)
    .join("\n");

  const content = `# Rhumb — Agent-Native Tool Intelligence
> https://rhumb.dev

## What is Rhumb?
Rhumb scores developer tools on how well they work for AI agents.
The AN (Agent-Native) Score measures execution reliability, access readiness,
and autonomy dimensions (payment, governance, web accessibility).

## For Agents
Install the MCP server for programmatic access:
  npx rhumb-mcp

Or use the CLI:
  npm install -g rhumb
  rhumb score stripe
  rhumb leaderboard payments --limit 5

## API Endpoints
- GET /v1/services — list all scored services
- GET /v1/services/{slug}/score — detailed score breakdown
- GET /v1/leaderboard/{category} — ranked services by category
- GET /v1/search?q={query} — semantic search

## Categories
${categoryList}

## Scored Services (${services.length} total)
${serviceList}

## Scoring Dimensions
### Execution (weight: 0.45)
I1 API Consistency, I2 Error Handling, I3 Idempotency, I4 Rate Limiting,
I5 Latency P99, I6 Schema Stability, I7 Documentation Quality,
I8 SDK Quality, I9 Webhook Reliability, I10 Versioning

### Access Readiness (weight: 0.40)
A1 Signup Friction, A2 Auth Complexity, A3 Free Tier,
A4 Key Provisioning, A5 Sandbox/Test Mode, A6 ToS Clarity

### Autonomy (weight: 0.15)
P1 Payment Autonomy — can agents pay programmatically? (x402, Stripe ACP, etc.)
G1 Governance Readiness — RBAC, audit logs, compliance certs
W1 Web Agent Accessibility — dashboard navigability for agents (AAG levels)

## Tier System
- L4 Native (7.5+): fully agent-ready
- L3 Ready (6.0–7.4): agent-usable with minor friction
- L2 Developing (5.0–5.9): significant gaps for agents
- L1 Limited (<5.0): human intervention required

## Links
- Website: https://rhumb.dev
- GitHub: https://github.com/supertrained/rhumb
- MCP Server: npx rhumb-mcp
`;

  return new Response(content, {
    headers: {
      "Content-Type": "text/plain; charset=utf-8",
      "Cache-Control": "public, max-age=3600, s-maxage=3600",
    },
  });
}

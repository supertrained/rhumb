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
The AN (Agent-Native) Score measures execution reliability and access readiness
across 20 dimensions. Scores are computed as 70% Execution + 30% Access Readiness.

## For Agents
Install the MCP server for programmatic access:
  npx rhumb-mcp

MCP tools available:
  find_tools("payment processing") — discover services by need
  get_score("stripe") — detailed AN Score breakdown
  get_alternatives("stripe") — comparable services ranked
  get_failure_modes("stripe") — known failure patterns

## API Endpoints
- GET /v1/services — list all scored services
- GET /v1/services/{slug}/score — detailed score breakdown
- GET /v1/leaderboard/{category} — ranked services by category
- GET /v1/search?q={query} — semantic search

## Categories
${categoryList}

## Scored Services (${services.length} total)
${serviceList}

## Scoring Formula
AN Score = (Execution × 0.70) + (Access Readiness × 0.30)

### Execution (70% of final score, 13 dimensions)
API reliability, error ergonomics, schema stability, latency distribution,
idempotency support, concurrent behavior, cold-start latency, output structure,
state leakage, graceful degradation, payment autonomy, governance readiness,
web agent accessibility.

### Access Readiness (30% of final score, 7 dimensions)
Signup autonomy, payment autonomy (access), provisioning speed,
credential management, rate limit transparency, documentation quality,
sandbox/test mode.

## Tier System
- L4 Native (8.0–10.0): built for agents, minimal friction
- L3 Ready (6.0–7.9): agents can use reliably with minor friction
- L2 Developing (4.0–5.9): usable with workarounds
- L1 Emerging (0.0–3.9): significant barriers to agent use

## Extended Context
- Full methodology: https://rhumb.dev/methodology
- Trust and provenance: https://rhumb.dev/trust
- About the team: https://rhumb.dev/about
- Score disputes: https://rhumb.dev/providers or providers@supertrained.ai
- Extended version: https://rhumb.dev/llms-full.txt

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

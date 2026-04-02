import type { APIRoute } from 'astro';
import { getServices, getCategories, getLeaderboard } from '../lib/api';

export const GET: APIRoute = async () => {
  const [services, categories] = await Promise.all([
    getServices(),
    getCategories(),
  ]);

  // Fetch leaderboard data for each category to get scores
  const categoryData = await Promise.all(
    categories.map(async (c) => {
      const lb = await getLeaderboard(c.slug, { limit: 50 });
      return { category: c, items: lb.error ? [] : lb.items };
    }),
  );

  const categoryList = categories
    .map((c) => `- /leaderboard/${c.slug} (${c.serviceCount} services)`)
    .join("\n");

  const serviceDetails = categoryData
    .map(({ category, items }) => {
      const label = category.slug.charAt(0).toUpperCase() + category.slug.slice(1);
      const header = `### ${label} (${items.length} scored)`;
      const rows = items
        .map(
          (item) =>
            `- **${item.name}** (${item.serviceSlug}): AN Score ${item.aggregateRecommendationScore?.toFixed(1) ?? "N/A"} | Execution ${item.executionScore?.toFixed(1) ?? "N/A"} | Access ${item.accessReadinessScore?.toFixed(1) ?? "N/A"} | Tier ${item.tier ?? "N/A"} → /service/${item.serviceSlug}`,
        )
        .join("\n");
      return `${header}\n${rows}`;
    })
    .join("\n\n");

  const content = `# Rhumb — Agent-Native Tool Intelligence (Full Context)
> https://rhumb.dev
> This is the extended version of llms.txt with per-service scores and details.
> Summary version: https://rhumb.dev/llms.txt

## What is Rhumb?
Rhumb scores developer tools on how well they work for AI agents — not humans
browsing documentation, but machines making API calls autonomously. Every score
is published, disputable, and transparent.

## Scoring Formula
AN Score = (Execution × 0.70) + (Access Readiness × 0.30)

20 dimensions across 2 axes. Execution covers API reliability, error handling,
schema stability, latency, idempotency, and end-to-end autonomy. Access
Readiness covers signup friction, credential management, rate limits, docs,
and sandbox availability.

## Tier System
- L4 Native (8.0–10.0): built for agents, minimal friction
- L3 Ready (6.0–7.9): agents can use reliably with minor friction
- L2 Developing (4.0–5.9): usable with workarounds
- L1 Emerging (0.0–3.9): significant barriers to agent use

## Programmatic Access
\`\`\`
npx rhumb-mcp@latest
\`\`\`
Tools: find_services, get_score, get_alternatives, get_failure_modes

## API
- GET /v1/services — all services
- GET /v1/services/{slug}/score — score breakdown
- GET /v1/leaderboard/{category} — ranked by category
- GET /v1/search?q={query} — semantic search

## Categories (${categories.length})
${categoryList}

## All Scored Services (${services.length} total)

${serviceDetails}

## Evidence Tiers
Each service has an evidence tier indicating the depth of evaluation:
- **Verified** (50+ evidence records): extensive runtime testing
- **Tested** (1-49 evidence records): some runtime evidence collected
- **Assessed** (0 evidence records): scored from documentation analysis
- **Pending**: not yet evaluated

## Trust & Methodology
- Full methodology: https://rhumb.dev/methodology
- Trust policy: https://rhumb.dev/trust
- Glossary: https://rhumb.dev/glossary
- About the team: https://rhumb.dev/about
- Score disputes: providers@supertrained.ai or GitHub issues

## Links
- Website: https://rhumb.dev
- GitHub: https://github.com/supertrained/rhumb
- MCP: npx rhumb-mcp@latest
- Twitter: https://x.com/pedrorhumb
`;

  return new Response(content, {
    headers: {
      "Content-Type": "text/plain; charset=utf-8",
      "Cache-Control": "public, max-age=3600, s-maxage=3600",
    },
  });
};

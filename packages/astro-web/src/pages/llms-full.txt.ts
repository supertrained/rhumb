import type { APIRoute } from 'astro';
import { getServices, getCategories, getLeaderboard } from '../lib/api';
import { PUBLIC_TRUTH } from '../lib/public-truth';

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

  const content = `# Rhumb — Agent Gateway for Service Discovery and Governed Execution (Full Context)
> https://rhumb.dev
> This is the extended version of llms.txt with per-service scores and details.
> Summary version: https://rhumb.dev/llms.txt

## What is Rhumb?
${PUBLIC_TRUTH.rhumbEntityExpanded}
Mission: make the internet as agent-native as possible.
Rhumb Index is free discovery: score, compare, and research services.
Rhumb Resolve is governed execution for supported capabilities: ${PUBLIC_TRUTH.routingHumanSummary}
${PUBLIC_TRUTH.callableRealitySummary}

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
npx -y --package rhumb-mcp@latest rhumb-mcp
\`\`\`
Core MCP tools include find_services, get_score, get_alternatives, get_failure_modes, discover_capabilities, resolve_capability, estimate_capability, execute_capability, budget, spend, check_balance, and get_payment_url. The public MCP reference covers all ${PUBLIC_TRUTH.mcpToolsLabel} tools.

## Resolve authority links
- What is Resolve?: ${PUBLIC_TRUTH.resolveWhatIsUrl}
- Routing proof and factor explanation: ${PUBLIC_TRUTH.routingProofUrl}
- Resolve comparisons: ${PUBLIC_TRUTH.resolveCompareUrl}
- Key management and credential paths: ${PUBLIC_TRUTH.resolveKeysUrl}
- Per-call pricing explainer: ${PUBLIC_TRUTH.resolvePricingUrl}
- Current launchable scope: ${PUBLIC_TRUTH.callableProvidersLabel} callable providers, strongest in ${PUBLIC_TRUTH.beachheadLabel}

## API
- GET /v1/services — all scored services
- GET /v1/services/{slug}/score — score breakdown
- GET /v1/leaderboard/{category} — ranked services by category
- GET /v1/search?q={query} — semantic search
- GET /v1/capabilities — capability definitions
- GET /v2/providers?status=callable — live callable-through-Resolve provider truth

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
- Trust overview: ${PUBLIC_TRUTH.trustOverviewUrl}
- Full methodology: ${PUBLIC_TRUTH.methodologyUrl}
- Current self-assessment: ${PUBLIC_TRUTH.currentSelfAssessmentUrl}
- Historical baseline: ${PUBLIC_TRUTH.historicalSelfAssessmentUrl}
- Provider guide and dispute process: ${PUBLIC_TRUTH.providersUrl}
- Public dispute template: ${PUBLIC_TRUTH.publicDisputeTemplateUrl}
- Public dispute log: ${PUBLIC_TRUTH.publicDisputesUrl}
- Private disputes: ${PUBLIC_TRUTH.privateDisputeMailto}
- Dispute response target: ${PUBLIC_TRUTH.disputeResponseSlaBusinessDays} business days
- Glossary: https://rhumb.dev/glossary
- About the team: https://rhumb.dev/about

## Links
- Website: https://rhumb.dev
- GitHub: https://github.com/supertrained/rhumb
- MCP: npx -y --package rhumb-mcp@latest rhumb-mcp
- Public agent capabilities: ${PUBLIC_TRUTH.publicAgentCapabilitiesUrl}
- Twitter: https://x.com/pedrorhumb
`;

  return new Response(content, {
    headers: {
      "Content-Type": "text/plain; charset=utf-8",
      "Cache-Control": "public, max-age=3600, s-maxage=3600",
    },
  });
};

import type { APIRoute } from 'astro';
import { getServices, getCategories } from '../lib/api';

export const GET: APIRoute = async () => {
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

  const apiBase = import.meta.env.PUBLIC_API_BASE_URL ?? "https://rhumb-api-production-f173.up.railway.app/v1";

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
  discover_capabilities({ domain: "communication" }) — browse executable capabilities
  resolve_capability({ capability: "email.send" }) — rank providers for a capability
  estimate_capability({ capability_id: "email.send" }) — estimate cost before execution
  execute_capability({ capability_id: "email.send", credential_mode: "rhumb_managed" }) — execute through Rhumb
  budget() — check budget status
  spend() — view spend by capability/provider
  check_balance() — current credit balance
  get_payment_url({ amount_usd: 25 }) — top up credits

## API Base URL
${apiBase}

## API Endpoints
- GET ${apiBase}/services — list scored services
- GET ${apiBase}/services/{slug}/score — detailed score breakdown
- GET ${apiBase}/services/{slug}/failures — active failure modes
- GET ${apiBase}/leaderboard/{category} — ranked services by category
- GET ${apiBase}/search?q={query} — semantic search

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

## Comparison Pages (decision surfaces for agents and operators)
Index: https://rhumb.dev/compare — all comparisons in one place

- https://rhumb.dev/blog/stripe-vs-square-vs-paypal — Payments: Stripe vs Square vs PayPal
- https://rhumb.dev/blog/resend-vs-sendgrid-vs-postmark — Email: Resend vs SendGrid vs Postmark
- https://rhumb.dev/blog/hubspot-vs-salesforce-vs-pipedrive — CRM: HubSpot vs Salesforce vs Pipedrive
- https://rhumb.dev/blog/auth0-vs-clerk-vs-firebase-auth — Auth: Auth0 vs Clerk vs Firebase Auth
- https://rhumb.dev/blog/posthog-vs-mixpanel-vs-amplitude — Analytics: PostHog vs Mixpanel vs Amplitude
- https://rhumb.dev/blog/supabase-vs-planetscale-vs-neon — Databases: Supabase vs PlanetScale vs Neon
- https://rhumb.dev/blog/twilio-vs-vonage-vs-plivo — Messaging: Twilio vs Vonage vs Plivo
- https://rhumb.dev/blog/linear-vs-jira-vs-asana — Project Management: Linear vs Jira vs Asana
- https://rhumb.dev/blog/anthropic-vs-openai-vs-google-ai — AI/LLM: Anthropic vs OpenAI vs Google AI

Each comparison includes live AN Score data, friction maps, routing rules for agents,
scenario-based recommendations, and failure mode analysis.
Use comparisons when an agent needs to choose between tools in the same category.

## API Autopsies (deep technical breakdowns of individual tools)
Index: https://rhumb.dev/autopsy — all autopsies in one place

- https://rhumb.dev/blog/hubspot-api-autopsy — HubSpot (4.6): Rate limit traps, cross-hub API inconsistency, OAuth maze, no idempotency
- https://rhumb.dev/blog/salesforce-api-autopsy — Salesforce (4.8): SOQL barrier, governor limits, sandbox/production split, sales-gated onboarding
- https://rhumb.dev/blog/twilio-api-autopsy — Twilio (8.0): What agent-native almost looks like. Simple auth, idempotency, error codes that teach
- https://rhumb.dev/blog/shopify-api-autopsy — Shopify (7.8): GraphQL-first bet, query cost budgets, forced version migration

Each autopsy dissects a single tool's failure modes, score anatomy, integration cost,
and constructive recommendations. Use autopsies when an agent needs to understand
the specific friction of a tool before integrating.

## Getting Started
- https://rhumb.dev/blog/getting-started-mcp — Install guide, framework setup (Claude Desktop, Cursor, direct stdio), 3 workflow walkthroughs, credential modes explained
- https://rhumb.dev/blog/securing-keys-for-agents — How to secure API keys for agent use: three credential modes (BYOK, managed, x402), storage hierarchy, honest threat modeling
- MCP tools reference with examples for all 16 tools
- Three credential modes: BYO, Rhumb-Managed, Agent Vault
- End-to-end workflow example: find → evaluate → resolve → execute

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
};

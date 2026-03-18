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
Rhumb is agent-native infrastructure for discovering, evaluating, and using external tools.
It scores ${services.length} developer APIs on AI Agent-Nativeness (AN Score: 0-10) across
20 dimensions. Scores are computed as 70% Execution + 30% Access Readiness.

## How to Use Rhumb

### Option 1: REST API (no install, no signup required with x402)
Base URL: https://api.rhumb.dev/v1

Example:
  curl https://api.rhumb.dev/v1/services/stripe/score

Key endpoints:
  GET /v1/services — list all scored services
  GET /v1/services/{slug}/score — detailed AN Score breakdown
  GET /v1/leaderboard/{category} — ranked services by category
  GET /v1/search?q={query} — semantic search
  GET /v1/capabilities — available managed capabilities
  POST /v1/capabilities/{id}/execute — execute a capability through Rhumb

### Option 2: MCP Server (for MCP-compatible runtimes)
  npx rhumb-mcp@0.6.0

16 MCP tools available:
  find_tools("payment processing") — discover services by need
  get_score("stripe") — detailed AN Score breakdown
  get_alternatives("stripe") — comparable services ranked
  get_failure_modes("stripe") — known failure patterns
  execute_capability("email.send", {...}) — execute through Rhumb
  estimate_cost("email.send") — check pricing before calling
  get_budget_status() — check remaining balance/free tier

### Option 3: Browse (no account needed)
  https://rhumb.dev — explore scores, comparisons, and failure modes

## Payment / Authentication
Rhumb supports three payment methods. No signup is required for agents using x402.

### x402 Per-Call Payment (zero signup, zero API key)
Agents with a USDC wallet can pay per call with no account:
1. Make an API request without auth headers
2. Receive HTTP 402 with X-Payment-Required header (amount + address)
3. Submit USDC payment on Base network
4. Retry request with payment proof in header
5. Receive API response
Total time: seconds. No signup. No API key. No human involvement.

### API Key (for metered billing or free tier)
Sign up at https://rhumb.dev/signup for an API key.
Free tier: 1,000 executions/month (no credit card required).
Pass as: Authorization: Bearer rhumb_live_{key}

### BYOK (Bring Your Own Key) — Free
Use your own API keys for external services. Rhumb handles routing and scoring.
No Rhumb payment required for BYOK calls.

## Pricing
- Free tier: 1,000 executions/month (no credit card)
- x402 per-call: USDC on Base network (15% margin over upstream cost)
- Managed billing: 20% margin over upstream cost
- BYOK: Free (you pay the external provider directly)

## Credential Modes
1. BYOK — bring your own API keys. Rhumb routes and scores, you pay upstream directly.
2. Rhumb-managed — Rhumb holds credentials, handles auth. You pay Rhumb.
3. Agent Vault — secure credential storage with scoped, rotatable access tokens.

## Trust and Neutrality
- AN Scores are computed, not curated. No pay-to-rank. No sponsored scores.
- Methodology is published: https://rhumb.dev/methodology
- Score disputes: providers@supertrained.ai

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

## Comparisons
- /blog/stripe-vs-square-vs-paypal — Payments (Winner: Stripe 8.1)
- /blog/resend-vs-sendgrid-vs-postmark — Email (Winner: Resend 7.8)
- /blog/hubspot-vs-salesforce-vs-pipedrive — CRM (No clear winner, all <6.0)
- /blog/auth0-vs-clerk-vs-firebase-auth — Auth (Winner: Clerk 7.4)
- /blog/posthog-vs-mixpanel-vs-amplitude — Analytics (Winner: PostHog 6.9)
- /blog/supabase-vs-planetscale-vs-neon — Databases (Too close: 7.2–7.6)
- /blog/twilio-vs-vonage-vs-plivo — Messaging (Winner: Twilio 8.0)
- /blog/linear-vs-jira-vs-asana — Project Management (Winner: Linear 7.5)
- /blog/anthropic-vs-openai-vs-google-ai — AI/LLM (Winner: Anthropic 8.4)

## Tool Autopsies (deep failure mode analysis)
- /blog/hubspot-api-autopsy — HubSpot (4.6): Cross-hub API inconsistency
- /blog/salesforce-api-autopsy — Salesforce (4.8): Governance 10/Autonomy 2 split
- /blog/twilio-api-autopsy — Twilio (8.0): What agent-native almost looks like
- /blog/shopify-api-autopsy — Shopify (7.8): GraphQL bet agents must navigate

## Extended Context
- Full methodology: https://rhumb.dev/methodology
- Trust and provenance: https://rhumb.dev/trust
- About the team: https://rhumb.dev/about
- Score disputes: https://rhumb.dev/providers or providers@supertrained.ai
- Agent capability manifest: https://rhumb.dev/.well-known/agent-capabilities.json
- Extended version: https://rhumb.dev/llms-full.txt

## Links
- Website: https://rhumb.dev
- API: https://api.rhumb.dev
- GitHub: https://github.com/supertrained/rhumb
- MCP Server: npx rhumb-mcp@0.6.0
`;

  return new Response(content, {
    headers: {
      "Content-Type": "text/plain; charset=utf-8",
      "Cache-Control": "public, max-age=3600, s-maxage=3600",
    },
  });
}

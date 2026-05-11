import type { APIRoute } from 'astro';
import { getServices, getCategories } from '../lib/api';
import { PRIMARY_ACTIVATION_PATHS } from '../lib/activation-paths';
import { PUBLIC_TRUTH } from '../lib/public-truth';

export const GET: APIRoute = async () => {
  const apiBase = import.meta.env.PUBLIC_API_BASE_URL ?? "https://api.rhumb.dev/v1";

  const [services, categories] = await Promise.all([
    getServices(),
    getCategories(),
  ]);
  const totalCapabilities = PUBLIC_TRUTH.capabilities;
  const routeList = PRIMARY_ACTIVATION_PATHS
    .map((route) => `- ${route.title}: https://rhumb.dev${route.href} — ${route.summary}`)
    .join("\n");

  const categoryList = categories
    .map((c) => `- /leaderboard/${c.slug} (${c.serviceCount} services)`)
    .join("\n");

  const serviceList = services
    .map((s) => `- /service/${s.slug} — ${s.description ?? s.name} [${s.category}]`)
    .join("\n");

  const content = `# Rhumb — Agent Gateway for Discovery and Governed Execution
> https://rhumb.dev

## What is Rhumb?
Rhumb is an agent gateway for discovery and governed execution.
Mission: make the internet as agent-native as possible.
Rhumb Index scores external services for AI-agent compatibility.
Rhumb Resolve executes supported capabilities through governed execution and routes each call to the best-fit provider for the call by first matching the supported capability path, then using AN Score, provider availability / circuit state, estimated cost, credential mode, latency proxy, and explicit policy constraints by default, while also allowing explicit provider choice when the agent wants direct control.

## System split: Index and Resolve
- Rhumb Index is free discovery: score, compare, and research services.
- Rhumb Resolve is per-call execution: route supported jobs through one governed surface.
- Agents can say what they want done or explicitly pin the provider/tool path they want.
- Index ranks the field. Resolve routes the call.

## How Resolve routes calls
- AN Score is a major routing input, not the sole routing rule.
- Resolve considers supported capability matching, provider availability / circuit state, estimated cost, credential mode, latency proxy, and explicit policy constraints before execution.
- Agents can still pin the provider/tool path explicitly when direct control is better than automatic routing.
- Discovery breadth is wider than current callable coverage, and Rhumb keeps that boundary explicit.

## Pick the right starting path
${routeList}

Service discovery answers who to trust.
Capability discovery answers what Rhumb can execute.
Signup creates identity. Credits or wallet-prefund unlock governed execution.

## Rhumb Resolve
Resolve is Rhumb’s governed execution layer for AI agents.
Index ranks the field.
Resolve routes each supported call to the best-fit provider for the call by default.
AN Score is a major routing input, not the sole routing rule.
Agents can also pin the supported provider path explicitly when they want direct control.
Supporting authority pages:
- What is Resolve?: ${PUBLIC_TRUTH.resolveWhatIsUrl}
- Routing proof and factor explanation: ${PUBLIC_TRUTH.routingProofUrl}
- Resolve comparisons: ${PUBLIC_TRUTH.resolveCompareUrl}
- Key management and credential paths: ${PUBLIC_TRUTH.resolveKeysUrl}
- Per-call pricing explainer: ${PUBLIC_TRUTH.resolvePricingUrl}
Current launchable scope: ${PUBLIC_TRUTH.callableProvidersLabel} callable providers, strongest in ${PUBLIC_TRUTH.beachheadLabel}.

## For Agents
Install the MCP server for programmatic access:
  npx -y --package rhumb-mcp@latest rhumb-mcp

MCP tools available:
  find_services({ query: "payment processing" }) — discover services by need
  get_score({ slug: "stripe" }) — detailed AN Score breakdown
  get_alternatives({ slug: "stripe" }) — comparable services ranked
  get_failure_modes({ slug: "stripe" }) — known failure patterns
  discover_capabilities({ domain: "communication" }) — browse capability definitions
  resolve_capability({ capability: "email.send", credential_mode: "byok" }) — rank providers, optionally scope to a credential mode, surface machine-readable recovery fields like recovery_hint.resolve_url, recovery_hint.credential_modes_url, and, when applicable, recovery_hint.alternate_execute_hint or recovery_hint.setup_handoff, and recover typoed capability IDs with search suggestions
  estimate_capability({ capability_id: "email.send", credential_mode: "rhumb_managed" }) — estimate the active execution rail, cost, and health before execution; anonymous direct system-of-record paths also preserve machine-readable execute_readiness handoffs
  execute_capability({ capability_id: "email.send", credential_mode: "rhumb_managed", body: { to: "user@example.com" } }) — execute through Rhumb
  budget({ action: "get" }) — check budget status
  spend({ period: "30d" }) — view spend by capability/provider
  check_balance() — current credit balance
  get_payment_url({ amount_usd: 25 }) — top up credits

## Honest current state
Discovery breadth is wider than current execution breadth.
Rhumb indexes ${PUBLIC_TRUTH.servicesLabel} scored services and ${PUBLIC_TRUTH.capabilitiesLabel} capability definitions.
Current governed execution is concentrated in ${PUBLIC_TRUTH.callableProvidersLabel} callable providers.

## API Base URL
${apiBase}

## Capabilities
Browse all ${totalCapabilities} capability definitions: https://rhumb.dev/capabilities
- GET ${apiBase}/capabilities?limit=100&offset=0 — paginated list of capability definitions
- GET ${apiBase}/capabilities?search=web+research — find the capability slug when you know the task but not the action ID
- Each capability: { id, domain, action, description, provider_count, top_provider }
- Capabilities are abstract actions (e.g. search.query, email.send) that map to concrete providers
- Use find_services() when the question is which vendor should I use
- Use discover_capabilities() when the question is what exact action slug should I call
- Use discover_capabilities() in MCP to browse, then resolve_capability() to compare ranked providers, optionally filter by credential mode, follow recovery_hint.resolve_url, recovery_hint.credential_modes_url, and, when applicable, recovery_hint.alternate_execute_hint or recovery_hint.setup_handoff when a filtered route dead-ends, and get search suggestions when the capability ID is wrong

## API Endpoints
- GET ${apiBase}/pricing - machine-readable public pricing contract
- GET ${apiBase}/capabilities?limit=100&offset=0 — browse capability definitions
- GET ${apiBase}/services — list scored services
- GET ${apiBase}/services/{slug}/score — detailed score breakdown
- GET ${apiBase}/services/{slug}/failures — active failure modes
- GET ${apiBase}/leaderboard/{category} — ranked services by category
- GET ${apiBase}/search?q={query} — semantic search

## Pricing
- Discovery (search, scores, browsing): Always free
- Execution rails: governed API key, wallet-prefund, or x402 per-call
- Provider-control modes where supported: BYOK and Agent Vault
- No subscriptions, no seat fees, no minimums
- Live pricing and markup terms: https://rhumb.dev/pricing
- What is Resolve?: ${PUBLIC_TRUTH.resolveWhatIsUrl}
- Routing proof and route-factor explanation: ${PUBLIC_TRUTH.routingProofUrl}
- Resolve comparisons: ${PUBLIC_TRUTH.resolveCompareUrl}
- Key management: ${PUBLIC_TRUTH.resolveKeysUrl}
- Per-call pricing explainer: ${PUBLIC_TRUTH.resolvePricingUrl}

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
- https://rhumb.dev/quickstart — Make your first API call in 30 seconds. Copy-paste examples for curl, JS, Python, MCP. No signup required for read endpoints.
- https://rhumb.dev/payments/agent — x402 agent payments: HTTP 402 flow, USDC on Base, wallet setup, and when to use on-chain per-call authorization
- https://rhumb.dev/blog/how-agents-actually-pay-x402-dogfood — x402 seller dogfood report: 5 compatibility mismatches, authorization proof vs tx_hash gap, and why structured 422 errors beat infinite 402 loops
- https://rhumb.dev/blog/getting-started-mcp — MCP install guide, framework setup (Claude Desktop, Cursor, direct stdio), 3 workflow walkthroughs, credential paths explained
- https://rhumb.dev/blog/securing-keys-for-agents — How to secure API keys for agent use: three credential paths (Rhumb-managed, BYOK, Agent Vault), storage hierarchy, honest threat modeling, and where x402 fits as a payment rail
- MCP tools reference with examples for all ${PUBLIC_TRUTH.mcpToolsLabel} tools
- Three credential paths: Rhumb-managed, BYOK, Agent Vault
- End-to-end workflow example: find → evaluate → resolve → execute

## Trust and disputes
- Trust overview: ${PUBLIC_TRUTH.trustOverviewUrl}
- Methodology: ${PUBLIC_TRUTH.methodologyUrl}
- Current self-assessment: ${PUBLIC_TRUTH.currentSelfAssessmentUrl}
- Historical baseline: ${PUBLIC_TRUTH.historicalSelfAssessmentUrl}
- Provider guide and dispute process: ${PUBLIC_TRUTH.providersUrl}
- Public dispute template: ${PUBLIC_TRUTH.publicDisputeTemplateUrl}
- Public dispute log: ${PUBLIC_TRUTH.publicDisputesUrl}
- Private disputes: ${PUBLIC_TRUTH.privateDisputeMailto}
- Dispute response target: ${PUBLIC_TRUTH.disputeResponseSlaBusinessDays} business days

## Extended Context
- Glossary: https://rhumb.dev/glossary
- About the team: https://rhumb.dev/about
- Extended version: https://rhumb.dev/llms-full.txt

## Links
- Website: https://rhumb.dev
- GitHub: https://github.com/supertrained/rhumb
- MCP Server: npx -y --package rhumb-mcp@latest rhumb-mcp
- Public agent capabilities: ${PUBLIC_TRUTH.publicAgentCapabilitiesUrl}
`;

  return new Response(content, {
    headers: {
      "Content-Type": "text/plain; charset=utf-8",
      "Cache-Control": "public, max-age=3600, s-maxage=3600",
    },
  });
};

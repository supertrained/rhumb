import { getServices, getCategories } from "../../lib/api";

export const revalidate = 3600;
export const maxDuration = 30;

export async function GET() {
  try {
    const [services, categories] = await Promise.all([
      getServices(),
      getCategories(),
    ]);

    const categoryLines: string[] = [];
    for (const c of categories) {
      categoryLines.push("- /leaderboard/" + c.slug + " (" + c.serviceCount + " services)");
    }
    const categoryList = categoryLines.join("\n");

    const serviceLines: string[] = [];
    for (const s of services) {
      const desc = s.description || s.name;
      serviceLines.push("- /service/" + s.slug + " — " + desc + " [" + s.category + "]");
    }
    const serviceList = serviceLines.join("\n");

    const parts: string[] = [];
    parts.push("# Rhumb — Agent-Native Tool Intelligence");
    parts.push("> https://rhumb.dev");
    parts.push("");
    parts.push("## What is Rhumb?");
    parts.push("Rhumb is agent-native infrastructure for discovering, evaluating, and using external tools.");
    parts.push("It scores " + services.length + " developer APIs on AI Agent-Nativeness (AN Score: 0-10) across");
    parts.push("20 dimensions. Scores are computed as 70% Execution + 30% Access Readiness.");
    parts.push("");
    parts.push("## How to Use Rhumb");
    parts.push("");
    parts.push("### Option 1: REST API (no install, no signup required with x402)");
    parts.push("Base URL: https://api.rhumb.dev/v1");
    parts.push("");
    parts.push("Example:");
    parts.push("  curl https://api.rhumb.dev/v1/services/stripe/score");
    parts.push("");
    parts.push("Key endpoints:");
    parts.push("  GET /v1/services — list all scored services");
    parts.push("  GET /v1/services/{slug}/score — detailed AN Score breakdown");
    parts.push("  GET /v1/leaderboard/{category} — ranked services by category");
    parts.push("  GET /v1/search?q={query} — semantic search");
    parts.push("  GET /v1/capabilities — available managed capabilities");
    parts.push("  POST /v1/capabilities/{id}/execute — execute a capability through Rhumb");
    parts.push("");
    parts.push("### Option 2: MCP Server (for MCP-compatible runtimes)");
    parts.push("  npx rhumb-mcp@latest");
    parts.push("");
    parts.push("16 MCP tools available:");
    parts.push('  find_services("payment processing") — discover services by need');
    parts.push('  get_score("stripe") — detailed AN Score breakdown');
    parts.push('  get_alternatives("stripe") — comparable services ranked');
    parts.push('  get_failure_modes("stripe") — known failure patterns');
    parts.push('  execute_capability("email.send", {...}) — execute through Rhumb');
    parts.push('  estimate_cost("email.send") — check pricing before calling');
    parts.push("  get_budget_status() — check remaining prepaid balance");
    parts.push("");
    parts.push("### Option 3: Browse (no account needed)");
    parts.push("  https://rhumb.dev — explore scores, comparisons, and failure modes");
    parts.push("");
    parts.push("## Payment / Authentication");
    parts.push("Rhumb supports three payment methods. No signup is required for agents using x402.");
    parts.push("");
    parts.push("### x402 Per-Call Payment (zero signup, zero API key)");
    parts.push("Agents with a USDC wallet can pay per call with no account:");
    parts.push("1. Make an API request without auth headers");
    parts.push("2. Receive HTTP 402 with X-Payment-Required header (amount + address)");
    parts.push("3. Submit USDC payment on Base network");
    parts.push("4. Retry request with payment proof in header");
    parts.push("5. Receive API response");
    parts.push("Total time: seconds. No signup. No API key. No human involvement.");
    parts.push("");
    parts.push("### API Key (for metered billing)");
    parts.push("Sign up at https://rhumb.dev/signup for an API key.");
    parts.push("Pay-as-you-go: per-call pricing. Check exact costs via the estimate endpoint before calling.");
    parts.push("Pass as: Authorization: Bearer rhumb_live_{key}");
    parts.push("");
    parts.push("### BYOK (Bring Your Own Key) — Free");
    parts.push("Use your own API keys for external services. Rhumb handles routing and scoring.");
    parts.push("No Rhumb payment required for BYOK calls.");
    parts.push("");
    parts.push("## Pricing");
    parts.push("- Discovery (search, scores, browsing): Always free");
    parts.push("- x402 per-call: USDC on Base network. Price returned in 402 response.");
    parts.push("- Managed billing: per-call. Use /capabilities/{id}/execute/estimate for exact cost.");
    parts.push("- BYOK: Free (you pay the external provider directly)");
    parts.push("");
    parts.push("## Credential Modes");
    parts.push("1. BYOK — bring your own API keys. Rhumb routes and scores, you pay upstream directly.");
    parts.push("2. Rhumb-managed — Rhumb holds credentials, handles auth. You pay Rhumb.");
    parts.push("3. Agent Vault — secure credential storage with scoped, rotatable access tokens.");
    parts.push("");
    parts.push("## Trust and Neutrality");
    parts.push("- AN Scores are computed, not curated. No pay-to-rank. No sponsored scores.");
    parts.push("- Methodology is published: https://rhumb.dev/methodology");
    parts.push("- Score disputes: providers@supertrained.ai");
    parts.push("");
    parts.push("## Categories");
    parts.push(categoryList);
    parts.push("");
    parts.push("## Scored Services (" + services.length + " total)");
    parts.push(serviceList);
    parts.push("");
    parts.push("## Scoring Formula");
    parts.push("AN Score = (Execution x 0.70) + (Access Readiness x 0.30)");
    parts.push("");
    parts.push("### Execution (70% of final score, 13 dimensions)");
    parts.push("API reliability, error ergonomics, schema stability, latency distribution,");
    parts.push("idempotency support, concurrent behavior, cold-start latency, output structure,");
    parts.push("state leakage, graceful degradation, payment autonomy, governance readiness,");
    parts.push("web agent accessibility.");
    parts.push("");
    parts.push("### Access Readiness (30% of final score, 7 dimensions)");
    parts.push("Signup autonomy, payment autonomy (access), provisioning speed,");
    parts.push("credential management, rate limit transparency, documentation quality,");
    parts.push("sandbox/test mode.");
    parts.push("");
    parts.push("## Tier System");
    parts.push("- L4 Native (8.0-10.0): built for agents, minimal friction");
    parts.push("- L3 Fluent (6.0-7.9): agents can use reliably with minor friction");
    parts.push("- L2 Developing (4.0-5.9): usable with workarounds");
    parts.push("- L1 Emerging (0.0-3.9): significant barriers to agent use");
    parts.push("");
    parts.push("## Comparisons");
    parts.push("- /blog/stripe-vs-square-vs-paypal — Payments (Winner: Stripe 8.1)");
    parts.push("- /blog/resend-vs-sendgrid-vs-postmark — Email (Winner: Resend 7.8)");
    parts.push("- /blog/hubspot-vs-salesforce-vs-pipedrive — CRM (No clear winner, all <6.0)");
    parts.push("- /blog/auth0-vs-clerk-vs-firebase-auth — Auth (Winner: Clerk 7.4)");
    parts.push("- /blog/posthog-vs-mixpanel-vs-amplitude — Analytics (Winner: PostHog 6.9)");
    parts.push("- /blog/supabase-vs-planetscale-vs-neon — Databases (Too close: 7.2-7.6)");
    parts.push("- /blog/twilio-vs-vonage-vs-plivo — Messaging (Winner: Twilio 8.0)");
    parts.push("- /blog/linear-vs-jira-vs-asana — Project Management (Winner: Linear 7.5)");
    parts.push("- /blog/anthropic-vs-openai-vs-google-ai — AI/LLM (Winner: Anthropic 8.4)");
    parts.push("- /blog/datadog-vs-new-relic-vs-grafana — Monitoring (Winner: Datadog 7.8)");
    parts.push("- /blog/vercel-vs-netlify-vs-render — DevOps/Deployment (Winner: Vercel 7.1)");
    parts.push("- /blog/s3-vs-r2-vs-b2 — Storage (Winner: AWS S3 8.1)");
    parts.push("");
    parts.push("## Tool Autopsies (deep failure mode analysis)");
    parts.push("- /blog/hubspot-api-autopsy — HubSpot (4.6): Cross-hub API inconsistency");
    parts.push("- /blog/salesforce-api-autopsy — Salesforce (4.8): Governance 10/Autonomy 2 split");
    parts.push("- /blog/twilio-api-autopsy — Twilio (8.0): What agent-native almost looks like");
    parts.push("- /blog/shopify-api-autopsy — Shopify (7.8): GraphQL bet agents must navigate");
    parts.push("");
    parts.push("## Self-Assessment");
    parts.push("- /blog/we-scored-ourselves — Rhumb (6.8): We applied our own methodology to ourselves.");
    parts.push("");
    parts.push("## Extended Context");
    parts.push("- Full methodology: https://rhumb.dev/methodology");
    parts.push("- Trust and provenance: https://rhumb.dev/trust");
    parts.push("- About the team: https://rhumb.dev/about");
    parts.push("- Score disputes: https://rhumb.dev/providers or providers@supertrained.ai");
    parts.push("- Agent capability manifest: https://rhumb.dev/.well-known/agent-capabilities.json");
    parts.push("- Extended version: https://rhumb.dev/llms-full.txt");
    parts.push("");
    parts.push("## Links");
    parts.push("- Website: https://rhumb.dev");
    parts.push("- API: https://api.rhumb.dev");
    parts.push("- GitHub: https://github.com/supertrained/rhumb");
    parts.push("- MCP Server: npx rhumb-mcp@latest");
    parts.push("");

    const content = parts.join("\n");

    return new Response(content, {
      headers: {
        "Content-Type": "text/plain; charset=utf-8",
        "Cache-Control": "public, max-age=3600, s-maxage=3600",
      },
    });
  } catch (err) {
    console.error("llms.txt failed:", err);
    return new Response(
      "# Rhumb — Agent-Native Tool Intelligence\n> https://rhumb.dev\n\nTemporarily unavailable. Visit https://rhumb.dev or use the API at https://api.rhumb.dev/v1\n",
      {
        status: 503,
        headers: { "Content-Type": "text/plain; charset=utf-8" },
      }
    );
  }
}

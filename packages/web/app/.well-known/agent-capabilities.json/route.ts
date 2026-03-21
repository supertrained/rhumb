import { getCapabilityCount, getCategories, getServiceCount } from "../../../lib/api";

export const revalidate = 3600; // Cache for 1 hour

export async function GET() {
  const [servicesScored, capabilities, categories] = await Promise.all([
    getServiceCount(),
    getCapabilityCount(),
    getCategories(),
  ]);

  const manifest = {
    name: "Rhumb",
    version: "0.3.2",
    description:
      `Agent-native infrastructure for discovering, evaluating, and using external tools. Scores ${servicesScored} APIs for AI agent compatibility (AN Score).`,
    url: "https://rhumb.dev",
    api: {
      base_url: "https://api.rhumb.dev/v1",
      docs: "https://api.rhumb.dev/docs",
      authentication: {
        methods: ["x402", "api_key", "byok"],
        x402: {
          description:
            "Zero-signup per-call payment. No API key or account required.",
          currency: "USDC",
          network: "Base",
          flow: "Send request → receive 402 with payment details → submit payment → retry with proof",
        },
        api_key: {
          description: "Bearer token from signup. Pay-as-you-go: upstream cost + 20% margin.",
          header: "Authorization: Bearer rhumb_live_{key}",
          signup_url: "https://rhumb.dev/signup",
        },
        byok: {
          description:
            "Bring your own API keys for external services. Free passthrough.",
        },
      },
    },
    mcp: {
      activation: "npx rhumb-mcp@0.6.0",
      tools: 16,
      tool_list: [
        "find_tools",
        "get_score",
        "get_alternatives",
        "get_failure_modes",
        "execute_capability",
        "estimate_cost",
        "get_budget_status",
        "get_ceremonies",
        "get_credentials",
        "get_ledger",
        "get_routing",
        "get_balance",
        "get_payment_url",
        "get_spend",
        "resolve_capability",
        "search_services",
      ],
    },
    coverage: {
      services_scored: servicesScored,
      capabilities,
      domains: categories.length,
      comparisons: 9,
      autopsies: 4,
    },
    pricing: {
      discovery: {
        cost: "free",
        includes: "search, scores, comparisons, browsing",
        signup_required: false,
      },
      x402: {
        margin: "15% over upstream cost",
        currency: "USDC",
        signup_required: false,
      },
      managed: {
        margin: "20% over upstream cost",
        signup_required: true,
      },
      byok: {
        cost: "free",
        description: "You pay external providers directly",
      },
    },
    trust: {
      neutrality: "Scores are computed, not curated. No pay-to-rank.",
      methodology: "https://rhumb.dev/methodology",
      disputes: "providers@supertrained.ai",
    },
    discovery: {
      llms_txt: "https://rhumb.dev/llms.txt",
      llms_full_txt: "https://rhumb.dev/llms-full.txt",
      agent_capabilities: "https://rhumb.dev/.well-known/agent-capabilities.json",
    },
    contact: {
      providers: "providers@supertrained.ai",
      github: "https://github.com/supertrained/rhumb",
    },
  };

  return new Response(JSON.stringify(manifest, null, 2), {
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "public, max-age=3600, s-maxage=3600",
      "Access-Control-Allow-Origin": "*",
    },
  });
}

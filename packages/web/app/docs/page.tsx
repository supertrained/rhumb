import type { Metadata } from "next";
import Link from "next/link";

import { ORDERED_SLUGS } from "../../lib/categories";
import { PUBLIC_TRUTH } from "../../lib/public-truth";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "API Documentation",
  description:
    "Rhumb REST API and MCP server docs for discovery, capability routing, execution, pricing, and receipts.",
  alternates: { canonical: "/docs" },
  openGraph: {
    title: "API Documentation — Rhumb",
    description: "REST API + MCP server docs for discovery, capability routing, execution, pricing, and receipts.",
    type: "website",
    url: "https://rhumb.dev/docs",
    siteName: "Rhumb",
  },
};

const BASE_URL = "https://api.rhumb.dev/v1";
const leaderboardCategoryCount = ORDERED_SLUGS.length;

const ENDPOINTS = [
  {
    method: "GET",
    path: "/v1/services",
    desc: "List all scored services",
    curl: `curl ${BASE_URL}/services`,
    response: `[
  {
    "slug": "stripe",
    "name": "Stripe",
    "category": "payments",
    "aggregate_recommendation_score": 8.09,
    "tier": "L4",
    "tier_label": "Native"
  },
  ...
]`,
  },
  {
    method: "GET",
    path: "/v1/services/{slug}/score",
    desc: "Full score breakdown for a service",
    curl: `curl ${BASE_URL}/services/stripe/score`,
    response: `{
  "slug": "stripe",
  "name": "Stripe",
  "aggregate_recommendation_score": 8.09,
  "execution_score": 9.0,
  "access_readiness_score": 6.6,
  "tier": "L4",
  "tier_label": "Native",
  "explanation": "Scores 8.1/10 overall...",
  "failure_modes": [
    {
      "title": "Restricted key scope confusion",
      "severity": "high",
      "agent_impact": "...",
      "workaround": "..."
    }
  ],
  "calculated_at": "2026-03-11T..."
}`,
  },
  {
    method: "GET",
    path: "/v1/services/{slug}/failures",
    desc: "Active failure modes for a service",
    curl: `curl ${BASE_URL}/services/stripe/failures`,
    response: `[
  {
    "title": "Restricted key scope confusion",
    "description": "...",
    "severity": "high",
    "frequency": "common",
    "agent_impact": "Agent creates key with insufficient scope...",
    "workaround": "Always request full scope list first...",
    "category": "authentication"
  }
]`,
  },
  {
    method: "GET",
    path: "/v1/leaderboard/{category}",
    desc: "Ranked services by category",
    curl: `curl ${BASE_URL}/leaderboard/payments`,
    response: `[
  {
    "slug": "stripe",
    "name": "Stripe",
    "aggregate_recommendation_score": 8.09,
    "tier": "L4",
    "rank": 1
  },
  {
    "slug": "lemon-squeezy",
    "name": "Lemon Squeezy",
    "aggregate_recommendation_score": 6.56,
    "tier": "L3",
    "rank": 2
  },
  ...
]`,
  },
  {
    method: "GET",
    path: "/v1/search?q={query}",
    desc: "Search services by name, category, or description",
    curl: `curl "${BASE_URL}/search?q=payment"`,
    response: `[
  {
    "slug": "stripe",
    "name": "Stripe",
    "category": "payments",
    "aggregate_recommendation_score": 8.09
  },
  ...
]`,
  },
];

const MCP_TOOLS = [
  {
    name: "find_services",
    desc: "Search indexed services by what you need them to do.",
    example: 'find_services({ query: "payment processing" })',
    category: "discovery",
  },
  {
    name: "get_score",
    desc: "Get the full AN Score breakdown for a service.",
    example: 'get_score({ slug: "stripe" })',
    category: "discovery",
  },
  {
    name: "get_alternatives",
    desc: "Find alternative services ranked by AN Score.",
    example: 'get_alternatives({ slug: "paypal" })',
    category: "discovery",
  },
  {
    name: "get_failure_modes",
    desc: "Get known failure patterns, impact, and workarounds for a service.",
    example: 'get_failure_modes({ slug: "stripe" })',
    category: "discovery",
  },
  {
    name: "discover_capabilities",
    desc: "Browse capability definitions by domain or search text.",
    example: 'discover_capabilities({ search: "email.send" })',
    category: "discovery",
  },
  {
    name: "resolve_capability",
    desc: "Resolve a capability to ranked providers, optional credential-mode filtering, machine-readable recovery fields like recovery_hint.resolve_url, recovery_hint.credential_modes_url, recovery_hint.alternate_execute_hint, and recovery_hint.setup_handoff, plus search suggestions when the capability ID is wrong.",
    example: 'resolve_capability({ capability: "email.send", credential_mode: "byok" })',
    category: "resolve",
  },
  {
    name: "estimate_capability",
    desc: "Estimate the active execution rail, cost, and health before execution. Anonymous direct system-of-record paths also preserve machine-readable execute_readiness handoffs.",
    example: 'estimate_capability({ capability_id: "email.send", credential_mode: "rhumb_managed" })',
    category: "resolve",
  },
  {
    name: "execute_capability",
    desc: "Execute a capability through Rhumb Resolve.",
    example: 'execute_capability({ capability_id: "email.send", credential_mode: "rhumb_managed", body: { to: "user@example.com", subject: "Hello" } })',
    category: "resolve",
  },
  {
    name: "credential_ceremony",
    desc: "Get step-by-step instructions for obtaining provider credentials.",
    example: 'credential_ceremony({ service: "gmail" })',
    category: "resolve",
  },
  {
    name: "check_credentials",
    desc: "Check which credential modes are available to you.",
    example: 'check_credentials({ capability: "email.send" })',
    category: "resolve",
  },
  {
    name: "budget",
    desc: "Check or set your call spending limit.",
    example: 'budget({ action: "get" })',
    category: "governance",
  },
  {
    name: "spend",
    desc: "Get spend totals and breakdowns by capability and provider.",
    example: 'spend({ period: "30d" })',
    category: "governance",
  },
  {
    name: "routing",
    desc: "Inspect or set provider routing preferences.",
    example: 'routing({ action: "get" })',
    category: "governance",
  },
  {
    name: "usage_telemetry",
    desc: "Get execution analytics for calls, latency, errors, and cost.",
    example: 'usage_telemetry({ days: 7 })',
    category: "governance",
  },
  {
    name: "check_balance",
    desc: "Check your current Rhumb credit balance.",
    example: "check_balance()",
    category: "governance",
  },
  {
    name: "get_payment_url",
    desc: "Get a checkout URL to top up credits.",
    example: 'get_payment_url({ amount_usd: 25 })',
    category: "governance",
  },
  {
    name: "get_ledger",
    desc: "Review billing events, top-ups, and debits.",
    example: 'get_ledger({ limit: 20 })',
    category: "governance",
  },
  {
    name: "rhumb_list_recipes",
    desc: "List the currently published Layer 3 recipe catalog.",
    example: "rhumb_list_recipes({ limit: 20 })",
    category: "recipes",
  },
  {
    name: "rhumb_get_recipe",
    desc: "Fetch the full published definition for a recipe.",
    example: 'rhumb_get_recipe({ recipe_id: "recipe.example" })',
    category: "recipes",
  },
  {
    name: "rhumb_recipe_execute",
    desc: "Execute a published Layer 3 recipe.",
    example: 'rhumb_recipe_execute({ recipe_id: "recipe.example", inputs: {} })',
    category: "recipes",
  },
  {
    name: "get_receipt",
    desc: "Retrieve a past execution receipt by ID.",
    example: 'get_receipt({ receipt_id: "rcpt_123" })',
    category: "audit",
  },
];

const MCP_TOOL_CATEGORIES = ["discovery", "resolve", "governance", "recipes", "audit"] as const;

export default function DocsPage() {
  return (
    <div className="bg-navy min-h-screen">
      <div className="max-w-4xl mx-auto px-6 pt-14 pb-24">
        {/* Header */}
        <header className="mb-16">
          <div className="flex items-center gap-3 mb-4">
            <span className="text-xs font-mono font-semibold text-amber uppercase tracking-widest">
              Documentation
            </span>
          </div>
          <h1 className="font-display font-bold text-3xl sm:text-4xl text-slate-100 leading-tight tracking-tight mb-6">
            API Documentation
          </h1>
          <p className="text-lg text-slate-400 leading-relaxed mb-6">
            Access discovery, capability routing, execution, pricing,
            and receipt surfaces programmatically. Discovery is public,
            while execution and billing require authentication.
          </p>
          <div className="bg-surface border border-slate-800 rounded-lg p-4 font-mono text-sm">
            <span className="text-slate-500">Base URL:</span>{" "}
            <span className="text-amber">{BASE_URL}</span>
          </div>

          <div className="mt-8 rounded-2xl border border-amber/20 bg-surface/80 p-5 backdrop-blur-sm">
            <p className="text-xs font-mono text-amber uppercase tracking-widest">
              Before you wire these routes into production
            </p>
            <p className="mt-3 text-sm text-slate-400 leading-relaxed">
              Check the trust posture, scoring methodology, and provider dispute path first so
              your docs stay honest before a score, ranking, or route choice turns into agent
              logic.
            </p>
            <div className="mt-4 flex flex-wrap gap-3 text-sm">
              <Link
                href="/trust"
                className="inline-flex rounded-lg border border-slate-700 px-4 py-2 text-slate-300 transition-colors duration-200 hover:border-slate-500 hover:text-slate-100"
              >
                Trust →
              </Link>
              <Link
                href="/methodology"
                className="inline-flex rounded-lg border border-slate-700 px-4 py-2 text-slate-300 transition-colors duration-200 hover:border-slate-500 hover:text-slate-100"
              >
                Methodology →
              </Link>
              <Link
                href="/providers#dispute-a-score"
                className="inline-flex rounded-lg border border-slate-700 px-4 py-2 text-slate-300 transition-colors duration-200 hover:border-slate-500 hover:text-slate-100"
              >
                Dispute a score →
              </Link>
            </div>
          </div>
        </header>

        {/* REST API */}
        <section className="mb-16">
          <h2 className="font-display font-bold text-2xl text-slate-100 mb-6 tracking-tight">
            REST API
          </h2>

          <div className="space-y-8">
            {ENDPOINTS.map((ep) => (
              <div
                key={ep.path}
                className="bg-surface border border-slate-800 rounded-xl overflow-hidden"
              >
                <div className="p-5 border-b border-slate-800">
                  <div className="flex items-center gap-3 mb-2">
                    <span className="font-mono text-xs font-bold text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded">
                      {ep.method}
                    </span>
                    <code className="font-mono text-sm text-slate-200">
                      {ep.path}
                    </code>
                  </div>
                  <p className="text-slate-400 text-sm">{ep.desc}</p>
                </div>

                <div className="p-5 border-b border-slate-800 bg-elevated">
                  <span className="text-[10px] font-mono text-slate-500 uppercase tracking-wider">
                    Request
                  </span>
                  <pre className="mt-2 text-sm font-mono text-slate-300 overflow-x-auto">
                    <code>{ep.curl}</code>
                  </pre>
                </div>

                <div className="p-5 bg-elevated">
                  <span className="text-[10px] font-mono text-slate-500 uppercase tracking-wider">
                    Response
                  </span>
                  <pre className="mt-2 text-sm font-mono text-slate-300 overflow-x-auto">
                    <code>{ep.response}</code>
                  </pre>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* MCP */}
        <section className="mb-16">
          <h2 className="font-display font-bold text-2xl text-slate-100 mb-6 tracking-tight">
            MCP Server
          </h2>
          <p className="text-slate-400 leading-relaxed mb-6">
            Rhumb provides an{" "}
            <a
              href="https://modelcontextprotocol.io"
              target="_blank"
              rel="noopener noreferrer"
              className="text-amber hover:underline underline-offset-2"
            >
              MCP
            </a>{" "}
            server that agents can use directly via the Model Context
            Protocol.
          </p>

          <div className="bg-surface border border-slate-800 rounded-xl p-5 mb-6">
            <span className="text-[10px] font-mono text-slate-500 uppercase tracking-wider">
              Install & run
            </span>
            <pre className="mt-3 text-sm font-mono text-slate-300 overflow-x-auto">
              <code>{`npx rhumb-mcp@latest`}</code>
            </pre>
          </div>

          <h3 className="font-display font-semibold text-lg text-slate-200 mb-4">
            Available tools ({MCP_TOOLS.length})
          </h3>

          {MCP_TOOL_CATEGORIES.map((cat) => {
            const tools = MCP_TOOLS.filter((t) => t.category === cat);
            const labels = {
              discovery: "Discovery (free)",
              resolve: "Resolve, estimate, and credential setup",
              governance: "Routing, usage, and billing",
              recipes: "Recipes (Layer 3 beta)",
              audit: "Receipts and audit",
            };
            return (
              <div key={cat} className="mb-8">
                <h4 className="font-mono text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3">
                  {labels[cat]}
                </h4>
                <div className="space-y-3">
                  {tools.map((tool) => (
                    <div
                      key={tool.name}
                      className="bg-surface border border-slate-800 rounded-lg p-4"
                    >
                      <div className="flex items-baseline gap-3 mb-1">
                        <code className="font-mono text-sm font-semibold text-amber">
                          {tool.name}
                        </code>
                      </div>
                      <p className="text-slate-400 text-sm mb-2">{tool.desc}</p>
                      <code className="font-mono text-xs text-slate-500 bg-elevated px-2 py-1 rounded">
                        {tool.example}
                      </code>
                    </div>
                  ))}
                </div>
              </div>
            );
          })}
        </section>

        {/* Notes */}
        <section className="bg-elevated border border-slate-800 rounded-xl p-6">
          <h2 className="font-display font-semibold text-lg text-slate-100 mb-3">
            Notes
          </h2>
          <ul className="space-y-2 text-slate-400 text-sm">
            <li className="flex items-start gap-2">
              <span className="text-amber mt-0.5">•</span>
              <span>
                <strong className="text-slate-200">
                  Discovery is free
                </strong>{" "}
                — search, scores, failure modes, and capability discovery
                require no authentication.
              </span>
            </li>
            <li className="flex items-start gap-2">
              <span className="text-amber mt-0.5">•</span>
              <span>
                <strong className="text-slate-200">
                  Execution requires a live rail
                </strong>{" "}
                — capability execution via Rhumb Resolve runs through
                governed API key, wallet-prefund, x402 per-call, or BYOK
                depending on the provider. Start with{" "}
                <code className="font-mono text-xs bg-surface px-1 rounded text-amber">
                  resolve_capability
                </code>{" "}
                to inspect the available credential modes, or sign up at{" "}
                <a
                  href="https://rhumb.dev/auth/login"
                  className="text-amber hover:underline underline-offset-2"
                >
                  rhumb.dev/auth/login
                </a>{" "}
                when you want the default governed API key path.
              </span>
            </li>
            <li className="flex items-start gap-2">
              <span className="text-amber mt-0.5">•</span>
              <span>
                <strong className="text-slate-200">JSON responses</strong>{" "}
                — all endpoints return JSON with standardized error
                envelopes including{" "}
                <code className="font-mono text-xs bg-surface px-1 rounded text-amber">
                  request_id
                </code>{" "}
                and{" "}
                <code className="font-mono text-xs bg-surface px-1 rounded text-amber">
                  resolution
                </code>
                .
              </span>
            </li>
            <li className="flex items-start gap-2">
              <span className="text-amber mt-0.5">•</span>
              <span>
                <strong className="text-slate-200">
                  {PUBLIC_TRUTH.categoriesLabel} scored categories
                </strong>{" "}
                — the ranked leaderboard hub currently covers {leaderboardCategoryCount} categories at{" "}
                <a
                  href="https://rhumb.dev/leaderboard"
                  className="text-amber hover:underline underline-offset-2"
                >
                  rhumb.dev/leaderboard
                </a>
              </span>
            </li>
            <li className="flex items-start gap-2">
              <span className="text-amber mt-0.5">•</span>
              <span>
                <strong className="text-slate-200">llms.txt</strong> — for
                agent discovery, see{" "}
                <a
                  href="https://rhumb.dev/llms.txt"
                  className="text-amber hover:underline underline-offset-2"
                >
                  rhumb.dev/llms.txt
                </a>
              </span>
            </li>
          </ul>
        </section>
      </div>
    </div>
  );
}

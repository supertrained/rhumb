import type { Metadata } from "next";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "API Documentation",
  description:
    "Rhumb REST API and MCP server documentation. Endpoints for service scores, failure modes, leaderboards, and search. No auth required.",
  alternates: { canonical: "/docs" },
  openGraph: {
    title: "API Documentation — Rhumb",
    description: "REST API + MCP server docs. Get AN Scores, failure modes, and leaderboards programmatically.",
    type: "website",
    url: "https://rhumb.dev/docs",
    siteName: "Rhumb",
  },
};

const BASE_URL = "https://api.rhumb.dev/v1";

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
  // Discovery tools (no auth required)
  {
    name: "find_services",
    desc: "Search for services by use case or need",
    example: 'find_services("payment processing")',
    category: "discovery",
  },
  {
    name: "get_score",
    desc: "Full AN Score breakdown for a specific service",
    example: 'get_score("stripe")',
    category: "discovery",
  },
  {
    name: "get_alternatives",
    desc: "Find scored alternatives in the same category",
    example: 'get_alternatives("paypal")',
    category: "discovery",
  },
  {
    name: "get_failure_modes",
    desc: "Known failure modes and workarounds for a service",
    example: 'get_failure_modes("stripe")',
    category: "discovery",
  },
  {
    name: "search_services",
    desc: "Semantic search across all scored services",
    example: 'search_services("email sending API")',
    category: "discovery",
  },
  {
    name: "get_ceremonies",
    desc: "Signup and onboarding friction for a service",
    example: 'get_ceremonies("sendgrid")',
    category: "discovery",
  },
  // Capability resolution tools (auth required for execution)
  {
    name: "resolve_capability",
    desc: "Find the best provider for a capability based on AN Score",
    example: 'resolve_capability("email.send")',
    category: "resolve",
  },
  {
    name: "execute_capability",
    desc: "Execute a capability through Rhumb's managed proxy",
    example: 'execute_capability("email.send", {to: "user@example.com", subject: "Hello"})',
    category: "resolve",
  },
  {
    name: "estimate_cost",
    desc: "Check pricing before executing a capability",
    example: 'estimate_cost("email.send")',
    category: "resolve",
  },
  {
    name: "get_credentials",
    desc: "Check available credential modes for a capability",
    example: 'get_credentials("email.send")',
    category: "resolve",
  },
  {
    name: "get_routing",
    desc: "See how a capability routes to providers",
    example: 'get_routing("scrape.extract")',
    category: "resolve",
  },
  // Billing & budget tools (auth required)
  {
    name: "get_budget_status",
    desc: "Check remaining prepaid balance and spend",
    example: "get_budget_status()",
    category: "billing",
  },
  {
    name: "get_balance",
    desc: "Current account balance",
    example: "get_balance()",
    category: "billing",
  },
  {
    name: "get_spend",
    desc: "Spend breakdown by service and time period",
    example: "get_spend()",
    category: "billing",
  },
  {
    name: "get_ledger",
    desc: "Transaction history and billing ledger",
    example: "get_ledger()",
    category: "billing",
  },
  {
    name: "get_payment_url",
    desc: "Get URL to add prepaid balance via Stripe",
    example: "get_payment_url()",
    category: "billing",
  },
];

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
            Access AN Scores, failure modes, and leaderboards
            programmatically. No authentication required.
          </p>
          <div className="bg-surface border border-slate-800 rounded-lg p-4 font-mono text-sm">
            <span className="text-slate-500">Base URL:</span>{" "}
            <span className="text-amber">{BASE_URL}</span>
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

          {(["discovery", "resolve", "billing"] as const).map((cat) => {
            const tools = MCP_TOOLS.filter((t) => t.category === cat);
            const labels = {
              discovery: "Discovery (no auth required)",
              resolve: "Capability Resolution (auth required for execution)",
              billing: "Billing & Budget (auth required)",
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
                — search, scores, leaderboards, and failure modes require
                no authentication.
              </span>
            </li>
            <li className="flex items-start gap-2">
              <span className="text-amber mt-0.5">•</span>
              <span>
                <strong className="text-slate-200">
                  Execution requires auth
                </strong>{" "}
                — capability execution via Rhumb Resolve requires an API
                key or x402 payment. Sign up at{" "}
                <a
                  href="https://rhumb.dev/auth/login"
                  className="text-amber hover:underline underline-offset-2"
                >
                  rhumb.dev/auth/login
                </a>
                .
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
                  92 categories
                </strong>{" "}
                — browse all at{" "}
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

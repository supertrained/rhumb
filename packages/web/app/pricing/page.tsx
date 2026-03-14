import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Pricing",
  description:
    "Rhumb scores are free. Forever. No auth required for AN Scores, leaderboards, service guides, MCP server, or API access.",
  alternates: { canonical: "/pricing" },
  openGraph: {
    title: "Pricing — Rhumb",
    description: "Scores are free. Forever. See what's included and what's coming.",
    type: "website",
    url: "https://rhumb.dev/pricing",
    siteName: "Rhumb",
  },
};

const TIERS = [
  {
    name: "Free",
    price: "$0",
    period: "forever",
    current: true,
    features: [
      "AN Scores for 53+ services",
      "Leaderboards across 11 categories",
      "Service integration guides for scored services",
      "MCP server (npx rhumb-mcp)",
      "Full REST API access",
      "Failure mode data",
      "llms.txt for agent discovery",
      "No auth required",
    ],
  },
  {
    name: "Pro",
    price: "TBD",
    period: "coming soon",
    current: false,
    features: [
      "Everything in Free",
      "Priority API access",
      "Score change webhooks",
      "Private failure mode reports",
      "Custom scoring for your stack",
      "API authentication + rate limit guarantee",
      "Email alerts on score changes",
    ],
  },
  {
    name: "Enterprise",
    price: "Custom",
    period: "coming soon",
    current: false,
    features: [
      "Everything in Pro",
      "Self-hosted scoring engine",
      "Custom scoring dimensions",
      "SLA + dedicated support",
      "Audit log access",
      "SSO + team management",
      "Private leaderboards",
    ],
  },
];

export default function PricingPage() {
  return (
    <div className="bg-navy min-h-screen">
      <div className="max-w-5xl mx-auto px-6 pt-14 pb-24">
        {/* Header */}
        <header className="text-center mb-16">
          <span className="text-xs font-mono font-semibold text-amber uppercase tracking-widest">
            Pricing
          </span>
          <h1 className="font-display font-bold text-3xl sm:text-4xl text-slate-100 leading-tight tracking-tight mt-4 mb-4">
            Scores are free. Forever.
          </h1>
          <p className="text-lg text-slate-400 leading-relaxed max-w-2xl mx-auto">
            AN Scores, leaderboards, failure modes, guides, the MCP server,
            and the full REST API — all free, no auth required. We&apos;ll
            charge for premium features when they exist.
          </p>
        </header>

        {/* Tier cards */}
        <div className="grid gap-6 sm:grid-cols-3 mb-16">
          {TIERS.map((tier) => (
            <div
              key={tier.name}
              className={`rounded-xl p-6 flex flex-col ${
                tier.current
                  ? "bg-surface border-2 border-amber/40 ring-1 ring-amber/10"
                  : "bg-surface border border-slate-800"
              }`}
            >
              <div className="mb-6">
                <div className="flex items-center gap-2 mb-3">
                  <h2 className="font-display font-bold text-xl text-slate-100">
                    {tier.name}
                  </h2>
                  {tier.current && (
                    <span className="text-[10px] font-mono font-semibold text-amber bg-amber/10 px-2 py-0.5 rounded-full uppercase tracking-wider">
                      Current
                    </span>
                  )}
                </div>
                <div className="flex items-baseline gap-1">
                  <span className="font-display font-bold text-3xl text-slate-100">
                    {tier.price}
                  </span>
                  <span className="text-slate-500 text-sm font-mono">
                    /{tier.period}
                  </span>
                </div>
              </div>

              <ul className="space-y-2.5 flex-1">
                {tier.features.map((f) => (
                  <li
                    key={f}
                    className="flex items-start gap-2.5 text-sm text-slate-400"
                  >
                    <span className="text-amber mt-0.5 text-xs">✓</span>
                    <span>{f}</span>
                  </li>
                ))}
              </ul>

              {tier.current ? (
                <a
                  href="https://rhumb-api-production-f173.up.railway.app/v1/services"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="mt-6 text-center px-4 py-2.5 rounded-lg bg-amber text-navy font-display font-semibold text-sm hover:bg-amber-dark transition-colors"
                >
                  Try the API →
                </a>
              ) : (
                <div className="mt-6 text-center px-4 py-2.5 rounded-lg bg-elevated border border-slate-700 text-slate-500 text-sm font-medium cursor-not-allowed">
                  Coming soon
                </div>
              )}
            </div>
          ))}
        </div>

        {/* Business model */}
        <section className="bg-surface border border-slate-800 rounded-xl p-8 max-w-3xl mx-auto">
          <h2 className="font-display font-bold text-xl text-slate-100 mb-4">
            How Rhumb makes money
          </h2>
          <div className="space-y-3 text-slate-400 text-sm leading-relaxed">
            <p>
              We plan to charge for premium features: score change webhooks,
              private failure mode reports, custom scoring dimensions, and
              enterprise self-hosted deployments.
            </p>
            <p>
              <strong className="text-slate-200">
                Core scores and the MCP server will always be free.
              </strong>
            </p>
            <p>
              We do not sell data. We do not accept payment for scores.
              Neutrality is our product — the moment we compromise it, we
              have nothing.
            </p>
          </div>
        </section>
      </div>
    </div>
  );
}

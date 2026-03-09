import type { Metadata } from "next";
import Link from "next/link";
import { getTierInfo } from "../../../lib/utils";

export const metadata: Metadata = {
  title: "Why Stripe Scores 8.3 and PayPal Scores 5.2 for AI Agents | Rhumb",
  description:
    "We scored 6 payment APIs on how well they work for AI agents — not humans. The results surprised us.",
  alternates: { canonical: "/blog/payments-for-agents" },
  openGraph: {
    title: "Why Stripe Scores 8.3 and PayPal Scores 5.2 for AI Agents",
    description:
      "We scored 6 payment APIs on how well they work for AI agents. The most popular one scored worst.",
    type: "article",
    publishedTime: "2026-03-09T00:00:00Z",
    authors: ["Pedro Nunes"],
    images: [{ url: "/blog/payments-for-agents/og", width: 1200, height: 630 }],
  },
};

// Payment tool data (from Rhumb AN Score v0.2)
const TOOLS = [
  {
    name: "Stripe",
    slug: "stripe",
    agg: 8.3,
    exec: 9.0,
    access: 6.6,
    tier: "L4",
    tierLabel: "Native",
    p50: 120,
    whyHigh:
      "Idempotency keys on every endpoint. Structured JSON errors with machine-readable codes. Webhook signatures with replay protection. API versioning via header — no URL breakage.",
    whyLow:
      "OAuth onboarding for Connect still requires human-in-the-loop. Dashboard-only features (dispute management, radar rules) have no API equivalent.",
  },
  {
    name: "Lemon Squeezy",
    slug: "lemon-squeezy",
    agg: 7.0,
    exec: 7.5,
    access: 5.7,
    tier: "L3",
    tierLabel: "Ready",
    p50: 105,
    whyHigh:
      "Clean REST API with consistent JSON responses. Good webhook support. Simple API key auth — no OAuth dance required.",
    whyLow:
      "Limited programmatic control over store setup. No idempotency keys. Error messages are human-readable strings, not machine-parseable codes. Fewer integration patterns than Stripe.",
  },
  {
    name: "Square",
    slug: "square",
    agg: 6.7,
    exec: 7.3,
    access: 5.2,
    tier: "L3",
    tierLabel: "Ready",
    p50: 140,
    whyHigh:
      "Solid SDK coverage. Idempotency keys available on create endpoints. GraphQL option for flexible queries.",
    whyLow:
      "OAuth flow mandatory for marketplace integrations. SDK error types inconsistent across languages. Higher latency on batch operations.",
  },
  {
    name: "Adyen",
    slug: "adyen",
    agg: 6.5,
    exec: 7.3,
    access: 4.7,
    tier: "L3",
    tierLabel: "Ready",
    p50: 155,
    whyHigh:
      "Enterprise-grade reliability. Comprehensive webhook events. Strong idempotency support.",
    whyLow:
      "Onboarding requires human sales contact. Test environment setup is manual. Documentation assumes human readers with prior payment domain knowledge.",
  },
  {
    name: "Braintree",
    slug: "braintree",
    agg: 5.8,
    exec: 6.5,
    access: 4.3,
    tier: "L2",
    tierLabel: "Developing",
    p50: 185,
    whyHigh: "PayPal ecosystem integration. Mature SDK with good type coverage.",
    whyLow:
      "XML error responses in some endpoints. Complex sandbox provisioning. Rate limits are opaque (no Retry-After header). Legacy API patterns mixed with modern ones.",
  },
  {
    name: "PayPal",
    slug: "paypal",
    agg: 5.2,
    exec: 5.9,
    access: 3.7,
    tier: "L2",
    tierLabel: "Developing",
    p50: 210,
    whyHigh:
      "Ubiquitous — virtually every user already has an account. REST API exists and covers core flows.",
    whyLow:
      "Error responses mix human strings with codes inconsistently. OAuth token rotation has undocumented edge cases. Webhook verification requires fetching a signing cert chain. Rate limits enforced silently (requests just fail). P50 latency 2x higher than Stripe. Sandbox environment frequently diverges from production behavior.",
  },
];

// Score bar for inline display
function MiniScoreBar({ value, max = 10 }: { value: number; max?: number }) {
  const tier = getTierInfo(value);
  const pct = Math.min((value / max) * 100, 100);
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 bg-slate-800 rounded-full overflow-hidden">
        <div className="h-full rounded-full" style={{ width: `${pct}%`, backgroundColor: tier.hex }} />
      </div>
      <span className={`font-mono font-bold text-sm w-7 text-right ${tier.textClass}`}>
        {value.toFixed(1)}
      </span>
    </div>
  );
}

export default function PaymentsForAgents() {
  return (
    <div className="bg-navy min-h-screen">
      <article className="max-w-3xl mx-auto px-6 pt-14 pb-24">

        {/* Article header */}
        <header className="mb-12">
          <div className="flex items-center gap-3 mb-6">
            <span className="text-xs font-mono font-semibold text-amber uppercase tracking-widest">
              Tool Autopsy
            </span>
            <span className="text-slate-700">·</span>
            <span className="text-xs font-mono text-slate-500">March 9, 2026</span>
            <span className="text-slate-700">·</span>
            <span className="text-xs font-mono text-slate-600">Pedro Nunes</span>
          </div>

          <h1 className="font-display font-bold text-3xl sm:text-4xl text-slate-100 leading-tight tracking-tight mb-6">
            Why Stripe Scores 8.3 and PayPal Scores 5.2 for AI Agents
          </h1>

          <p className="text-lg text-slate-400 leading-relaxed border-l-2 border-amber/50 pl-4">
            We scored 6 payment APIs on how well they work for AI agents — not humans.
            The most popular one scored the worst.
          </p>
        </header>

        {/* Intro */}
        <section className="prose-rhumb mb-12">
          <p>
            When a human picks a payment processor, they compare pricing pages, read case studies,
            and ask their network. When an AI agent picks one, it needs to know:{" "}
            <em>Can I call this API without getting stuck?</em>
          </p>
          <p>
            &quot;Great documentation&quot; means nothing when your user is a language model. What
            matters is: Are errors machine-readable? Are operations idempotent? Can I retry safely
            without human intervention?
          </p>
          <p>
            We built the{" "}
            <Link href="/leaderboard/payments" className="text-amber hover:underline underline-offset-2">
              Agent-Native Score
            </Link>{" "}
            to answer this. Here&apos;s what we found when we scored the 6 most common payment
            APIs that agents actually use.
          </p>
        </section>

        {/* Leaderboard summary */}
        <section className="mb-12">
          <h2 className="font-display font-semibold text-xl text-slate-100 mb-5">The Leaderboard</h2>

          <div className="bg-surface border border-slate-800 rounded-xl overflow-hidden">
            {TOOLS.map((tool, i) => {
              const tier = getTierInfo(tool.agg);
              return (
                <div
                  key={tool.slug}
                  className={`flex items-center gap-4 px-5 py-4 transition-colors hover:bg-elevated ${
                    i < TOOLS.length - 1 ? "border-b border-slate-800" : ""
                  }`}
                >
                  {/* Rank */}
                  <span className="font-mono text-sm text-slate-600 w-5 shrink-0">#{i + 1}</span>

                  {/* Score badge */}
                  <div
                    className={`w-11 h-11 rounded-full flex flex-col items-center justify-center border shrink-0 ${tier.bgClass} ${tier.borderClass} ${tier.glowClass}`}
                  >
                    <span className={`font-mono font-bold text-sm leading-none ${tier.textClass}`}>
                      {tool.agg.toFixed(1)}
                    </span>
                  </div>

                  {/* Name + tier */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <Link
                        href={`/service/${tool.slug}`}
                        className="font-display font-semibold text-slate-100 hover:text-amber transition-colors"
                      >
                        {tool.name}
                      </Link>
                      <span
                        className={`text-xs font-mono px-1.5 py-0.5 rounded border ${tier.bgClass} ${tier.borderClass} ${tier.textClass}`}
                      >
                        {tool.tier} {tool.tierLabel}
                      </span>
                    </div>
                    <div className="mt-1 flex gap-4 text-xs font-mono text-slate-600">
                      <span>Exec: {tool.exec.toFixed(1)}</span>
                      <span>Access: {tool.access.toFixed(1)}</span>
                      <span>P50: {tool.p50}ms</span>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>

          <p className="mt-3 text-xs font-mono text-slate-600">
            Agent-Native Score v0.2 · Execution (70%) + Access (30%) · Higher is better ·{" "}
            <Link href="/leaderboard/payments" className="text-amber hover:underline">
              Full leaderboard →
            </Link>
          </p>
        </section>

        {/* Individual breakdowns */}
        {TOOLS.map((tool) => {
          const tier = getTierInfo(tool.agg);
          return (
            <section key={tool.slug} className="mb-10">
              <div className="flex items-baseline gap-3 mb-4">
                <h2 className="font-display font-bold text-xl text-slate-100">
                  <Link
                    href={`/service/${tool.slug}`}
                    className="hover:text-amber transition-colors"
                  >
                    {tool.name}
                  </Link>
                </h2>
                <span className={`font-mono font-bold text-lg ${tier.textClass}`}>
                  {tool.agg.toFixed(1)}
                </span>
                <span className={`text-xs font-mono px-1.5 py-0.5 rounded border ${tier.bgClass} ${tier.borderClass} ${tier.textClass}`}>
                  {tool.tier}
                </span>
              </div>

              {/* Score bars */}
              <div className="mb-4 bg-surface border border-slate-800 rounded-lg p-4 space-y-2.5">
                <div className="flex items-center gap-3">
                  <span className="text-xs font-mono text-slate-500 w-14 shrink-0">Execution</span>
                  <div className="flex-1"><MiniScoreBar value={tool.exec} /></div>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-xs font-mono text-slate-500 w-14 shrink-0">Access</span>
                  <div className="flex-1"><MiniScoreBar value={tool.access} /></div>
                </div>
                <div className="pt-1 border-t border-slate-800 text-xs font-mono text-slate-600">
                  P50 latency: <span className="text-slate-400">{tool.p50}ms</span>
                </div>
              </div>

              <div className="prose-rhumb space-y-3">
                <p>
                  <span className="text-score-native font-semibold">What works for agents:</span>{" "}
                  {tool.whyHigh}
                </p>
                <p>
                  <span className="text-score-limited font-semibold">Where agents get stuck:</span>{" "}
                  {tool.whyLow}
                </p>
              </div>
            </section>
          );
        })}

        {/* Key insight */}
        <section className="my-12 bg-surface border border-l-4 border-amber rounded-xl p-7">
          <h2 className="font-display font-bold text-lg text-amber mb-4">The Pattern</h2>
          <div className="prose-rhumb">
            <p>
              The gap between Stripe (8.3) and PayPal (5.2) isn&apos;t about features — both
              process payments. It&apos;s about{" "}
              <strong>execution ergonomics</strong>: idempotency, structured errors, retry safety,
              and predictable latency.
            </p>
            <p>
              Stripe was built API-first. PayPal was built for checkout buttons and added an API
              later. That architectural decision from 2011 still shows up in every agent interaction
              in 2026.
            </p>
            <p>
              For AI automation teams: if your agent is spending tokens parsing error messages or
              implementing custom retry logic, the tool isn&apos;t saving you time. It&apos;s
              costing you compute.
            </p>
          </div>
        </section>

        {/* Methodology */}
        <section className="mb-12">
          <h2 className="font-display font-bold text-lg text-slate-100 mb-4">Methodology</h2>
          <div className="prose-rhumb">
            <p>
              The <strong>Agent-Native Score</strong> evaluates tools across 17 dimensions grouped
              into Execution (how well the API works when called) and Access (how easy it is for an
              agent to start using it autonomously). Scores are weighted 70/30 Execution/Access.
            </p>
            <p>
              Key dimensions include: schema stability, error ergonomics, idempotency guarantees,
              latency distribution (P50/P95/P99), cold-start behavior, token cost of integration,
              and graceful degradation under load.
            </p>
            <p>
              All scores are based on live probe data, not documentation review.{" "}
              <Link href="/leaderboard/payments" className="text-amber hover:underline">
                View the full payments leaderboard →
              </Link>
            </p>
          </div>
        </section>

        {/* CTA */}
        <section className="bg-surface border border-slate-800 rounded-xl p-8 text-center">
          <h2 className="font-display font-bold text-xl text-slate-100 mb-3">
            Want to see how your tools stack up?
          </h2>
          <p className="text-slate-400 text-sm mb-6">
            We&apos;ve scored 50+ developer tools across 10 categories.
          </p>
          <Link
            href="/leaderboard"
            className="inline-flex px-6 py-3 rounded-lg bg-amber text-navy font-display font-semibold text-sm hover:bg-amber-dark transition-colors duration-200"
          >
            Browse all categories →
          </Link>
        </section>

      </article>
    </div>
  );
}

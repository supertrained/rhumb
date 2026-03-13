import React from "react";
import type { Metadata } from "next";
import Link from "next/link";

import { buildTrackedOutboundHref } from "../../lib/tracking";

export const metadata: Metadata = {
  title: "For API Providers",
  description:
    "Your service was scored by Rhumb. Learn what the AN Score measures, how to improve your score, and how to dispute it.",
  alternates: { canonical: "/providers" },
  openGraph: {
    title: "For API Providers — Rhumb",
    description: "You got scored. Here's what that means — and how to engage with the process.",
    type: "website",
    url: "https://rhumb.dev/providers",
    siteName: "Rhumb",
  },
};

const IMPROVEMENTS = [
  {
    title: "Machine-readable error codes",
    desc: "Return structured error responses with stable error codes, not human-readable strings. Include retry-after headers on rate limits.",
    impact: "High — affects Error Ergonomics, Graceful Degradation",
  },
  {
    title: "Structured JSON responses",
    desc: "Consistent, well-typed JSON with stable schemas. Avoid freeform text fields where structured data would work.",
    impact: "High — affects Output Structure Quality, Schema Stability",
  },
  {
    title: "Idempotency key support",
    desc: "Allow clients to pass idempotency keys for safe retries on state-mutating operations. Critical for payment and data-mutation endpoints.",
    impact: "High — affects Idempotency dimension",
  },
  {
    title: "Sandbox / test mode for agents",
    desc: "Provide a test environment that mirrors production behavior. Agents need to validate integrations without real consequences.",
    impact: "Medium — affects Sandbox/Test Mode dimension",
  },
  {
    title: "Programmatic credential lifecycle",
    desc: "API key creation, rotation, and scoping via API — not just a dashboard. Agents can't click buttons.",
    impact: "Medium — affects Credential Management, Signup Autonomy",
  },
  {
    title: "Machine-parseable documentation",
    desc: "OpenAPI specs, well-organized API references, code examples. Reduce the token cost for agents to understand your API.",
    impact: "Medium — affects Documentation Quality",
  },
  {
    title: "Transparent rate limits",
    desc: "Publish limits. Return rate-limit headers (X-RateLimit-Remaining, Retry-After). Predictable throttling beats surprise 429s.",
    impact: "Medium — affects Rate Limit Transparency",
  },
];

const FAQ = [
  {
    q: "Is this pay-to-play?",
    a: "No. Scores cannot be bought, and we do not accept payment for higher rankings. Our business model charges for premium features (webhooks, private reports, enterprise tools) — never for score changes. Neutrality is our product.",
  },
  {
    q: "Can I remove my listing?",
    a: "No — public APIs are scored as public information. However, you can dispute specific scores or data points, and every dispute is reviewed. If something is factually wrong, we'll fix it.",
  },
  {
    q: "How often are scores updated?",
    a: "Currently, scores are updated when we process new documentation or receive dispute feedback. We are building toward continuous monitoring with automated re-scoring.",
  },
  {
    q: "Who decides the scores?",
    a: "Scores are calculated algorithmically based on 17 dimensions. The methodology is published at /methodology. Currently scores are documentation-derived; we are building toward observed execution scoring.",
  },
  {
    q: "Can I contribute data to improve my score?",
    a: "Yes — if your documentation doesn't reflect current capabilities, file a dispute with evidence. We prioritize accuracy over everything.",
  },
  {
    q: "My score seems unfair. What can I do?",
    a: "File a dispute via GitHub issue (public) or email providers@supertrained.ai (private). Include specific data points you believe are incorrect and why. We review every dispute.",
  },
];

export default function ProvidersPage() {
  const githubDisputeHref = buildTrackedOutboundHref({
    destinationUrl: "https://github.com/supertrained/rhumb/issues/new?template=score-dispute.md",
    eventType: "github_dispute_click",
    pagePath: "/providers",
    sourceSurface: "providers_page",
  });
  const privateDisputeHref = buildTrackedOutboundHref({
    destinationUrl: "mailto:providers@supertrained.ai?subject=Score%20Dispute%20(Private)",
    eventType: "dispute_click",
    pagePath: "/providers",
    sourceSurface: "providers_page",
  });
  const contactHref = buildTrackedOutboundHref({
    destinationUrl: "mailto:providers@supertrained.ai",
    eventType: "contact_click",
    pagePath: "/providers",
    sourceSurface: "providers_page",
  });

  return (
    <div className="bg-navy min-h-screen">
      <div className="max-w-3xl mx-auto px-6 pt-14 pb-24">
        {/* Header */}
        <header className="mb-16">
          <span className="text-xs font-mono font-semibold text-amber uppercase tracking-widest">
            For Providers
          </span>
          <h1 className="font-display font-bold text-3xl sm:text-4xl text-slate-100 leading-tight tracking-tight mt-4 mb-6">
            You got scored.
            <br />
            <span className="text-slate-400">
              Here&apos;s what that means.
            </span>
          </h1>
          <p className="text-lg text-slate-400 leading-relaxed">
            Rhumb scores developer tools on how well they work for
            autonomous AI agents. If you&apos;re a provider and your
            service appears on our{" "}
            <Link
              href="/leaderboard"
              className="text-amber hover:underline underline-offset-2"
            >
              leaderboard
            </Link>
            , here&apos;s what you need to know.
          </p>
        </header>

        {/* What we measure */}
        <section className="mb-16">
          <h2 className="font-display font-bold text-2xl text-slate-100 mb-4 tracking-tight">
            What we measure
          </h2>
          <p className="text-slate-400 leading-relaxed mb-4">
            The{" "}
            <Link
              href="/methodology"
              className="text-amber hover:underline underline-offset-2"
            >
              AN Score
            </Link>{" "}
            evaluates your API across 17 dimensions on three axes:
            Execution (reliability, error handling, schema stability),
            Access Readiness (signup friction, payment rails, docs quality),
            and Autonomy (end-to-end agent operability).
          </p>
          <p className="text-slate-400 leading-relaxed">
            We&apos;re not rating your product for humans. We&apos;re
            rating it for machines. A beautiful dashboard doesn&apos;t help
            an agent that needs machine-readable error codes at 2 AM.
          </p>
        </section>

        {/* How to improve */}
        <section className="mb-16">
          <h2 className="font-display font-bold text-2xl text-slate-100 mb-6 tracking-tight">
            How to improve your score
          </h2>
          <div className="space-y-4">
            {IMPROVEMENTS.map((item) => (
              <div
                key={item.title}
                className="bg-surface border border-slate-800 rounded-lg p-5"
              >
                <h3 className="font-display font-semibold text-base text-slate-100 mb-1">
                  {item.title}
                </h3>
                <p className="text-slate-400 text-sm leading-relaxed mb-2">
                  {item.desc}
                </p>
                <span className="text-xs font-mono text-amber/70">
                  {item.impact}
                </span>
              </div>
            ))}
          </div>
        </section>

        {/* Dispute */}
        <section className="mb-16">
          <h2 className="font-display font-bold text-2xl text-slate-100 mb-4 tracking-tight">
            Dispute a score
          </h2>
          <p className="text-slate-400 leading-relaxed mb-4">
            If you believe a score is inaccurate, we want to know.
            Disputes can be filed publicly or privately:
          </p>
          <div className="flex flex-wrap gap-3 mb-4">
            <a
              href={githubDisputeHref}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex px-4 py-2.5 rounded-lg bg-surface border border-slate-700 text-slate-200 text-sm font-medium hover:border-amber/40 transition-colors"
            >
              Public: GitHub issue →
            </a>
            <a
              href={privateDisputeHref}
              className="inline-flex px-4 py-2.5 rounded-lg bg-surface border border-slate-700 text-slate-200 text-sm font-medium hover:border-amber/40 transition-colors"
            >
              Private: Email →
            </a>
          </div>
          <p className="text-slate-500 text-sm">
            Every dispute is reviewed. Public disputes and outcomes are
            tracked on GitHub. Private disputes are handled via email — we
            won&apos;t publish your correspondence without permission.
          </p>
        </section>

        {/* FAQ */}
        <section className="mb-16">
          <h2 className="font-display font-bold text-2xl text-slate-100 mb-6 tracking-tight">
            Provider FAQ
          </h2>
          <div className="space-y-4">
            {FAQ.map((item) => (
              <div
                key={item.q}
                className="bg-surface border border-slate-800 rounded-lg p-5"
              >
                <h3 className="font-display font-semibold text-base text-slate-100 mb-2">
                  {item.q}
                </h3>
                <p className="text-slate-400 text-sm leading-relaxed">
                  {item.a}
                </p>
              </div>
            ))}
          </div>
        </section>

        {/* CTA */}
        <section className="bg-surface border border-amber/20 rounded-xl p-8 text-center">
          <h2 className="font-display font-bold text-xl text-slate-100 mb-3">
            Want to talk?
          </h2>
          <p className="text-slate-400 text-sm mb-6 max-w-lg mx-auto">
            We&apos;re building this to help agents — and by extension, to
            help providers build better agent-compatible products. We&apos;d
            love to hear from you.
          </p>
          <a
            href={contactHref}
            className="inline-flex px-6 py-3 rounded-lg bg-amber text-navy font-display font-semibold text-sm hover:bg-amber-dark transition-colors duration-200"
          >
            providers@supertrained.ai
          </a>
        </section>
      </div>
    </div>
  );
}

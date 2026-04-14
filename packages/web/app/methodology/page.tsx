import React from "react";
import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "How We Score — AN Score Methodology",
  description:
    "Full methodology behind Rhumb's Agent-Native Score. 20 dimensions across 2 axes — Execution (70%) and Access Readiness (30%). Open, auditable, disputable.",
  alternates: { canonical: "/methodology" },
  openGraph: {
    title: "AN Score Methodology",
    description:
      "20 dimensions, 2 axes, fully transparent scoring. How Rhumb rates developer tools for AI agent compatibility.",
    type: "website",
    url: "https://rhumb.dev/methodology",
    siteName: "Rhumb",
  },
};

const FAQ_JSON_LD = {
  "@context": "https://schema.org",
  "@type": "FAQPage",
  mainEntity: [
    {
      "@type": "Question",
      name: "How does Rhumb score APIs?",
      acceptedAnswer: {
        "@type": "Answer",
        text: "Rhumb uses 20 dimensions across 2 axes (Execution 70%, Access Readiness 30%) to produce an Agent-Native Score from 0-10. Execution includes 10 core dimensions plus 3 autonomy dimensions. Access Readiness covers 7 dimensions.",
      },
    },
    {
      "@type": "Question",
      name: "Are Rhumb scores based on real testing?",
      acceptedAnswer: {
        "@type": "Answer",
        text: "Current scores are documentation-derived. We are building toward observed agent execution scoring and are transparent about this limitation.",
      },
    },
    {
      "@type": "Question",
      name: "Can I dispute a Rhumb score?",
      acceptedAnswer: {
        "@type": "Answer",
        text: "Yes. File a dispute via GitHub issue or email providers@supertrained.ai. Every dispute is reviewed and the outcome is public.",
      },
    },
  ],
};

const EXECUTION_DIMS = [
  {
    name: "API Reliability",
    desc: "Uptime, error rate consistency, and graceful handling of edge cases under normal and peak load.",
  },
  {
    name: "Error Ergonomics",
    desc: "Machine-readable error codes, structured error responses, retry-after headers. Can an agent self-heal from errors without human interpretation?",
  },
  {
    name: "Schema Stability",
    desc: "Mean time between breaking changes (MTBBC). How often does the response shape change without warning?",
  },
  {
    name: "Latency Distribution",
    desc: "P50, P95, P99 latency — not averages. P99 determines whether agents timeout and corrupt state.",
  },
  {
    name: "Idempotency",
    desc: "Support for idempotency keys, safe retries. Critical for payment and state-mutating operations.",
  },
  {
    name: "Concurrent Behavior",
    desc: "How the API handles simultaneous connections — queue, reject, or silent drop. Silent drops are worst: they look like success.",
  },
  {
    name: "Cold-Start Latency",
    desc: "First-request latency vs. warm latency. Serverless cold starts on idle APIs affect agent timeout budgets.",
  },
  {
    name: "Output Structure Quality",
    desc: "Structured JSON vs. freeform text responses. Structured output reduces downstream compute for consuming agents.",
  },
  {
    name: "State Leakage",
    desc: "Implicit caching returning stale data across sequential calls. Agents need predictable, stateless responses.",
  },
  {
    name: "Graceful Degradation",
    desc: "Slow responses under load vs. hard 503 cutoffs. Agents can handle slow; they can't handle surprise disconnections.",
  },
];

const ACCESS_DIMS = [
  {
    name: "Signup Autonomy",
    desc: "Can an agent create an account without a human clicking through OAuth, CAPTCHA, or email verification?",
  },
  {
    name: "Payment Autonomy",
    desc: "Agent-compatible payment rails — API billing, consumption-based pricing, programmatic payment methods.",
  },
  {
    name: "Provisioning Speed",
    desc: "Time from 'I want to use this' to 'I have working credentials.' Minutes matter for autonomous agents.",
  },
  {
    name: "Credential Management",
    desc: "API key rotation, scoped tokens, programmatic credential lifecycle management.",
  },
  {
    name: "Rate Limit Transparency",
    desc: "Published limits, machine-readable rate limit headers, predictable throttling behavior.",
  },
  {
    name: "Documentation Quality",
    desc: "Machine-parseable docs, OpenAPI specs, code examples in multiple languages, token cost of context.",
  },
  {
    name: "Sandbox/Test Mode",
    desc: "Dedicated test environments for agents to validate integrations without production consequences.",
  },
];

const AUTONOMY_DIMS = [
  {
    name: "Payment Integration",
    desc: "Native billing APIs, consumption pricing, Stripe Issuing support, programmatic everything.",
  },
  {
    name: "Governance & Compliance",
    desc: "Programmatic ToS acceptance, audit trails, compliance certifications accessible via API.",
  },
  {
    name: "Web Agent Accessibility",
    desc: "How well the provider's web interface works for browser-controlling agents (a11y tree quality, semantic HTML, keyboard navigability).",
  },
];

const TIERS = [
  {
    level: "L1",
    name: "Opaque",
    range: "0.0 – 3.9",
    color: "text-red-400",
    bg: "bg-red-500/10",
    border: "border-red-500/20",
    desc: "Significant barriers to agent use. Missing basic machine-readability.",
  },
  {
    level: "L2",
    name: "Developing",
    range: "4.0 – 5.9",
    color: "text-amber",
    bg: "bg-amber/10",
    border: "border-amber/20",
    desc: "Usable with workarounds. Some dimensions are strong, others need work.",
  },
  {
    level: "L3",
    name: "Ready",
    range: "6.0 – 7.9",
    color: "text-blue-400",
    bg: "bg-blue-500/10",
    border: "border-blue-500/20",
    desc: "Agents can use this tool reliably. Minor friction points remain.",
  },
  {
    level: "L4",
    name: "Native",
    range: "8.0 – 10.0",
    color: "text-emerald-400",
    bg: "bg-emerald-500/10",
    border: "border-emerald-500/20",
    desc: "Built for agents. Excellent across all dimensions. The gold standard.",
  },
];

export default function MethodologyPage() {
  return (
    <div className="bg-navy min-h-screen">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(FAQ_JSON_LD) }}
      />

      <div className="max-w-4xl mx-auto px-6 pt-14 pb-24">
        {/* Header */}
        <header className="mb-16">
          <div className="flex items-center gap-3 mb-4">
            <span className="text-xs font-mono font-semibold text-amber uppercase tracking-widest">
              Methodology
            </span>
            <span className="text-slate-700">·</span>
            <span className="text-xs font-mono text-slate-500">
              AN Score
            </span>
          </div>
          <h1 className="font-display font-bold text-3xl sm:text-4xl text-slate-100 leading-tight tracking-tight mb-6">
            How We Score
          </h1>
          <p className="text-lg text-slate-400 leading-relaxed">
            The Agent-Native Score rates developer tools on how well they
            work for autonomous AI agents. 20 dimensions, 2 axes, fully
            transparent.
          </p>
        </header>

        {/* Philosophy */}
        <section className="mb-16">
          <h2 className="font-display font-bold text-2xl text-slate-100 mb-4 tracking-tight">
            Philosophy
          </h2>
          <div className="space-y-4 text-slate-400 leading-relaxed">
            <p>
              &ldquo;Agent-native&rdquo; means evaluating tools from the
              agent&apos;s perspective — not a human reading documentation,
              but an autonomous program making API calls, parsing responses,
              handling errors, and deciding what to do next.
            </p>
            <p>
              Human-oriented review sites ask: &ldquo;Is the dashboard
              intuitive?&rdquo; We ask:{" "}
              <strong className="text-slate-200">
                &ldquo;When this API returns a 429, does the response
                include a machine-readable retry-after header, or does the
                agent have to parse a human-readable error string?&rdquo;
              </strong>
            </p>
          </div>
        </section>

        {/* Agent-native parity */}
        <section className="mb-16">
          <h2 className="font-display font-bold text-2xl text-slate-100 mb-4 tracking-tight">
            Agent-native parity
          </h2>
          <div className="bg-surface border border-slate-800 rounded-xl p-6 space-y-4">
            <p className="text-slate-400 text-sm leading-relaxed">
              This page explains the scoring system in human language, but the
              method should not be trapped here. The same model is exposed in
              machine-readable form through Rhumb&apos;s public interfaces.
            </p>
            <ul className="space-y-3 text-sm text-slate-400 leading-relaxed">
              <li>
                <strong className="text-slate-200">llms.txt:</strong>{" "}
                <Link href="/llms.txt" className="text-amber hover:underline underline-offset-2">
                  discover the available routes and tools
                </Link>
              </li>
              <li>
                <strong className="text-slate-200">Docs:</strong>{" "}
                <Link href="/docs" className="text-amber hover:underline underline-offset-2">
                  API and MCP usage
                </Link>{" "}
                for programmatic retrieval of scores, alternatives, and failure modes
              </li>
              <li>
                <strong className="text-slate-200">Service pages:</strong> each score page links back to methodology,
                trust, self-score, and dispute flow so provenance is visible at
                the moment of evaluation
              </li>
            </ul>
          </div>
        </section>

        {/* Two Axes */}
        <section className="mb-16">
          <h2 className="font-display font-bold text-2xl text-slate-100 mb-6 tracking-tight">
            Two scoring axes
          </h2>
          <div className="grid gap-4 sm:grid-cols-2">
            {[
              {
                name: "Execution",
                weight: "70%",
                desc: "How reliably the tool works when an agent calls it. Covers API stability, error handling, latency, schema consistency, and end-to-end autonomy (payment, compliance, web accessibility).",
                count: "13 dimensions",
              },
              {
                name: "Access Readiness",
                weight: "30%",
                desc: "How easy it is for an agent to start using the tool. Signup friction, payment rails, credential management, documentation, and sandbox availability.",
                count: "7 dimensions",
              },
            ].map((axis) => (
              <div
                key={axis.name}
                className="bg-surface border border-slate-800 rounded-xl p-6"
              >
                <div className="flex items-baseline justify-between mb-3">
                  <h3 className="font-display font-semibold text-lg text-slate-100">
                    {axis.name}
                  </h3>
                  <span className="font-mono text-amber text-sm font-semibold">
                    {axis.weight}
                  </span>
                </div>
                <p className="text-slate-400 text-sm leading-relaxed mb-3">
                  {axis.desc}
                </p>
                <span className="text-xs font-mono text-slate-600">
                  {axis.count}
                </span>
              </div>
            ))}
          </div>
        </section>

        {/* Dimensions */}
        <section className="mb-16">
          <h2 className="font-display font-bold text-2xl text-slate-100 mb-6 tracking-tight">
            The 20 dimensions
          </h2>

          <h3 className="font-display font-semibold text-lg text-slate-200 mb-4 mt-8">
            Execution{" "}
            <span className="text-slate-600 font-normal text-sm">
              (10 core dimensions · part of 70% Execution axis)
            </span>
          </h3>
          <div className="space-y-3">
            {EXECUTION_DIMS.map((d) => (
              <div
                key={d.name}
                className="bg-surface border border-slate-800 rounded-lg p-4"
              >
                <h4 className="font-mono text-sm font-semibold text-slate-200 mb-1">
                  {d.name}
                </h4>
                <p className="text-slate-400 text-sm leading-relaxed">
                  {d.desc}
                </p>
              </div>
            ))}
          </div>

          <h3 className="font-display font-semibold text-lg text-slate-200 mb-4 mt-10">
            Access Readiness{" "}
            <span className="text-slate-600 font-normal text-sm">
              (7 dimensions · 30% weight)
            </span>
          </h3>
          <div className="space-y-3">
            {ACCESS_DIMS.map((d) => (
              <div
                key={d.name}
                className="bg-surface border border-slate-800 rounded-lg p-4"
              >
                <h4 className="font-mono text-sm font-semibold text-slate-200 mb-1">
                  {d.name}
                </h4>
                <p className="text-slate-400 text-sm leading-relaxed">
                  {d.desc}
                </p>
              </div>
            ))}
          </div>

          <h3 className="font-display font-semibold text-lg text-slate-200 mb-4 mt-10">
            Autonomy{" "}
            <span className="text-slate-600 font-normal text-sm">
              (3 dimensions · included in 70% Execution axis)
            </span>
          </h3>
          <div className="space-y-3">
            {AUTONOMY_DIMS.map((d) => (
              <div
                key={d.name}
                className="bg-surface border border-slate-800 rounded-lg p-4"
              >
                <h4 className="font-mono text-sm font-semibold text-slate-200 mb-1">
                  {d.name}
                </h4>
                <p className="text-slate-400 text-sm leading-relaxed">
                  {d.desc}
                </p>
              </div>
            ))}
          </div>
        </section>

        {/* Tiers */}
        <section className="mb-16">
          <h2 className="font-display font-bold text-2xl text-slate-100 mb-6 tracking-tight">
            Tier system
          </h2>
          <div className="space-y-3">
            {TIERS.map((t) => (
              <div
                key={t.level}
                className={`${t.bg} ${t.border} border rounded-xl p-5 flex items-start gap-4`}
              >
                <span
                  className={`font-mono text-sm font-bold ${t.color} min-w-[2.5rem]`}
                >
                  {t.level}
                </span>
                <div>
                  <div className="flex items-baseline gap-3">
                    <h3
                      className={`font-display font-semibold text-base ${t.color}`}
                    >
                      {t.name}
                    </h3>
                    <span className="font-mono text-xs text-slate-500">
                      {t.range}
                    </span>
                  </div>
                  <p className="text-slate-400 text-sm mt-1">{t.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* Data Sources */}
        <section className="mb-16">
          <h2 className="font-display font-bold text-2xl text-slate-100 mb-4 tracking-tight">
            Data sources & limitations
          </h2>
          <div className="bg-elevated border border-amber/20 rounded-xl p-6">
            <div className="flex items-start gap-3">
              <span className="text-amber text-lg">⚠</span>
              <div className="space-y-3 text-slate-400 leading-relaxed text-sm">
                <p>
                  <strong className="text-slate-200">
                    Current scores are documentation-derived.
                  </strong>{" "}
                  This means they reflect what{" "}
                  <em className="text-slate-300">should</em> work based on
                  published documentation, not what{" "}
                  <em className="text-slate-300">actually</em> works when
                  tested in practice.
                </p>
                <p>
                  We are transparent about this because trust requires
                  honesty. Documentation-derived scoring provides broad
                  coverage quickly (53 services in 10 days), but it cannot
                  catch undocumented rate limits, silent schema changes, or
                  production behavior that diverges from docs.
                </p>
                <p>
                  <strong className="text-slate-200">Roadmap:</strong>{" "}
                  Observed agent execution scoring — real agents making
                  real API calls — is our next major milestone. Until a
                  score is explicitly labeled with a stronger evidence
                  source, assume it is{" "}
                  <code className="font-mono text-xs bg-surface px-1.5 py-0.5 rounded text-amber">
                    Documentation-derived
                  </code>
                  . We will only use runtime-oriented labels when the
                  underlying evidence exists and is linked publicly.
                </p>
              </div>
            </div>
          </div>
        </section>

        {/* Dispute */}
        <section className="bg-surface border border-slate-800 rounded-xl p-8">
          <h2 className="font-display font-bold text-xl text-slate-100 mb-3">
            Dispute a score
          </h2>
          <p className="text-slate-400 text-sm leading-relaxed mb-4">
            Disagree with a score? We want to hear about it. Every dispute
            is reviewed, and the outcome is public.
          </p>
          <div className="flex flex-wrap gap-3">
            <a
              href="https://github.com/supertrained/rhumb/issues/new?template=score-dispute.md"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex px-4 py-2 rounded-lg bg-elevated border border-slate-700 text-slate-200 text-sm font-medium hover:border-amber/40 transition-colors"
            >
              Open a GitHub issue →
            </a>
            <a
              href="mailto:providers@supertrained.ai?subject=Score%20Dispute"
              className="inline-flex px-4 py-2 rounded-lg bg-elevated border border-slate-700 text-slate-200 text-sm font-medium hover:border-amber/40 transition-colors"
            >
              Email privately →
            </a>
            <Link
              href="/providers#dispute-a-score"
              className="inline-flex px-4 py-2 rounded-lg bg-elevated border border-slate-700 text-slate-200 text-sm font-medium hover:border-amber/40 transition-colors"
            >
              Read the dispute process →
            </Link>
          </div>
          <p className="text-slate-500 text-xs leading-relaxed mt-4">
            We target an initial response within 5 business days and keep public outcomes visible on GitHub.
          </p>
        </section>
      </div>
    </div>
  );
}

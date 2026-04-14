import React from "react";
import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Why Trust Rhumb?",
  description:
    "Rhumb's trust model: open methodology, self-scoring, dispute process, CC BY 4.0 data license, and transparent limitations.",
  alternates: { canonical: "/trust" },
  openGraph: {
    title: "Why Trust Rhumb?",
    description: "Open methodology. Self-scoring. Disputable. Here's why you can trust the AN Score.",
    type: "website",
    url: "https://rhumb.dev/trust",
    siteName: "Rhumb",
  },
};

const TRUST_SIGNALS = [
  {
    icon: "⚖",
    title: "Neutrality is non-negotiable",
    content:
      "Scores cannot be bought. We do not accept payment for higher scores. Our pricing model charges for operations (API access, webhooks, enterprise features) — never for outcomes (score changes). This is a hard boundary, not a preference.",
  },
  {
    icon: "🔬",
    title: "We scored ourselves first",
    content: null,
    contentJsx: true,
  },
  {
    icon: "📖",
    title: "Open methodology",
    content: null,
    contentJsx: true,
  },
  {
    icon: "⚡",
    title: "Dispute any score",
    content:
      "Disagree with a score? File a dispute via GitHub issue or email. Every dispute is reviewed, and outcomes are public. We don't hide from criticism — we use it to improve.",
  },
  {
    icon: "📄",
    title: "CC BY 4.0 data license",
    content:
      "All scores and failure modes are licensed Creative Commons Attribution 4.0 International. Use them, cite them, build on them. The data is yours to use — we just ask for attribution.",
  },
  {
    icon: "⚠",
    title: "Honest about limitations",
    content: null,
    contentJsx: true,
  },
];

export default function TrustPage() {
  return (
    <div className="bg-navy min-h-screen">
      <div className="max-w-3xl mx-auto px-6 pt-14 pb-24">
        {/* Header */}
        <header className="mb-16">
          <span className="text-xs font-mono font-semibold text-amber uppercase tracking-widest">
            Trust
          </span>
          <h1 className="font-display font-bold text-3xl sm:text-4xl text-slate-100 leading-tight tracking-tight mt-4 mb-6">
            Why trust Rhumb?
          </h1>
          <p className="text-lg text-slate-400 leading-relaxed">
            A scoring system is only as good as its integrity. Here&apos;s
            how we earn trust — and what we&apos;re still working on.
          </p>
        </header>

        {/* Agent-native trust */}
        <section className="mb-16">
          <h2 className="font-display font-bold text-2xl text-slate-100 mb-4 tracking-tight">
            Trust should be inspectable
          </h2>
          <div className="bg-surface border border-slate-800 rounded-xl p-6 space-y-4">
            <p className="text-slate-400 text-sm leading-relaxed">
              Agent-native trust means we do not ask humans or agents to rely on
              vibes. Each trust claim on this page should resolve to a public,
              inspectable artifact.
            </p>
            <ul className="space-y-3 text-sm text-slate-400 leading-relaxed">
              <li>
                <strong className="text-slate-200">Method:</strong>{" "}
                <Link href="/methodology" className="text-amber hover:underline underline-offset-2">
                  published methodology
                </Link>
              </li>
              <li>
                <strong className="text-slate-200">Self-audit:</strong>{" "}
                <Link href="/blog/self-score" className="text-amber hover:underline underline-offset-2">
                  Rhumb scored itself first
                </Link>
              </li>
              <li>
                <strong className="text-slate-200">Machine-readable entry point:</strong>{" "}
                <Link href="/llms.txt" className="text-amber hover:underline underline-offset-2">
                  llms.txt
                </Link>{" "}
                and{" "}
                <Link href="/docs" className="text-amber hover:underline underline-offset-2">
                  docs
                </Link>
              </li>
              <li>
                <strong className="text-slate-200">Dispute path:</strong>{" "}
                <Link href="/providers#dispute-a-score" className="text-amber hover:underline underline-offset-2">
                  provider guide
                </Link>{" "}
                with public GitHub template, private email path, and a 5-business-day response target
              </li>
            </ul>
          </div>
        </section>

        {/* Trust signals */}
        <div className="space-y-8">
          {/* Neutrality */}
          <div className="bg-surface border border-slate-800 rounded-xl p-6">
            <div className="flex items-start gap-4">
              <span className="text-2xl">⚖</span>
              <div>
                <h2 className="font-display font-semibold text-lg text-slate-100 mb-2">
                  Neutrality is non-negotiable
                </h2>
                <p className="text-slate-400 text-sm leading-relaxed">
                  Scores cannot be bought. We do not accept payment for
                  higher scores. Our pricing model charges for operations
                  (API access, webhooks, enterprise features) — never for
                  outcomes (score changes). This is a hard boundary, not a
                  preference.
                </p>
              </div>
            </div>
          </div>

          {/* Self-scoring */}
          <div className="bg-surface border border-slate-800 rounded-xl p-6">
            <div className="flex items-start gap-4">
              <span className="text-2xl">🔬</span>
              <div>
                <h2 className="font-display font-semibold text-lg text-slate-100 mb-2">
                  We scored ourselves first
                </h2>
                <p className="text-slate-400 text-sm leading-relaxed">
                  Before scoring anyone else, we ran the AN Score
                  methodology on Rhumb itself. We scored{" "}
                  <strong className="text-slate-200">
                    3.5 out of 10 (L1 Limited)
                  </strong>{" "}
                  and{" "}
                  <Link
                    href="/blog/self-score"
                    className="text-amber hover:underline underline-offset-2"
                  >
                    published the full breakdown
                  </Link>
                  . If we can&apos;t be honest about our own shortcomings,
                  why would you trust our assessment of anyone else?
                </p>
              </div>
            </div>
          </div>

          {/* Open methodology */}
          <div className="bg-surface border border-slate-800 rounded-xl p-6">
            <div className="flex items-start gap-4">
              <span className="text-2xl">📖</span>
              <div>
                <h2 className="font-display font-semibold text-lg text-slate-100 mb-2">
                  Open methodology
                </h2>
                <p className="text-slate-400 text-sm leading-relaxed">
                  Our{" "}
                  <Link
                    href="/methodology"
                    className="text-amber hover:underline underline-offset-2"
                  >
                    scoring methodology
                  </Link>{" "}
                  is fully documented — 20 dimensions, 2 axes, tier
                  definitions, data sources, limitations. You can read
                  exactly how every score is calculated. The code is{" "}
                  <a
                    href="https://github.com/supertrained/rhumb"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-amber hover:underline underline-offset-2"
                  >
                    open source (MIT)
                  </a>
                  .
                </p>
              </div>
            </div>
          </div>

          {/* Dispute */}
          <div className="bg-surface border border-slate-800 rounded-xl p-6">
            <div className="flex items-start gap-4">
              <span className="text-2xl">⚡</span>
              <div>
                <h2 className="font-display font-semibold text-lg text-slate-100 mb-2">
                  Dispute any score
                </h2>
                <p className="text-slate-400 text-sm leading-relaxed">
                  Disagree with a score? File a dispute via{" "}
                  <a
                    href="https://github.com/supertrained/rhumb/issues/new?template=score-dispute.md"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-amber hover:underline underline-offset-2"
                  >
                    GitHub issue template
                  </a>{" "}
                  or{" "}
                  <a
                    href="mailto:providers@supertrained.ai?subject=Score%20Dispute"
                    className="text-amber hover:underline underline-offset-2"
                  >
                    email
                  </a>
                  . Every dispute is reviewed, we aim to respond within 5 business days, and public outcomes live on{" "}
                  <a
                    href="https://github.com/supertrained/rhumb/issues?q=is%3Aissue+%22Score+dispute%3A%22"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-amber hover:underline underline-offset-2"
                  >
                    GitHub
                  </a>
                  . We don&apos;t hide from criticism — we use it to improve.
                </p>
              </div>
            </div>
          </div>

          {/* Data license */}
          <div className="bg-surface border border-slate-800 rounded-xl p-6">
            <div className="flex items-start gap-4">
              <span className="text-2xl">📄</span>
              <div>
                <h2 className="font-display font-semibold text-lg text-slate-100 mb-2">
                  CC BY 4.0 data license
                </h2>
                <p className="text-slate-400 text-sm leading-relaxed">
                  All scores and failure modes are licensed{" "}
                  <strong className="text-slate-200">
                    Creative Commons Attribution 4.0 International
                  </strong>
                  . Use them in your research, embed them in your products,
                  cite them in your papers. We just ask for attribution.
                </p>
              </div>
            </div>
          </div>

          {/* Limitations */}
          <div className="bg-elevated border border-amber/20 rounded-xl p-6">
            <div className="flex items-start gap-4">
              <span className="text-2xl">⚠</span>
              <div>
                <h2 className="font-display font-semibold text-lg text-slate-100 mb-2">
                  Honest about limitations
                </h2>
                <div className="space-y-3 text-slate-400 text-sm leading-relaxed">
                  <p>
                    Most scores start as{" "}
                    <strong className="text-slate-200">
                      documentation-derived
                    </strong>
                    , built from published API docs and provider claims.
                    These capture what should work, but cannot catch
                    undocumented behaviors, silent schema changes, or
                    production edge cases.
                  </p>
                  <p>
                    We are actively closing this gap.{" "}
                    <strong className="text-slate-200">
                      Over 20% of our reviews are now runtime-backed
                    </strong>
                    {" "}— supported by real evidence from agent execution,
                    tester-generated probes, and live API calls. Every
                    review labels its evidence source. You can inspect
                    the evidence behind any score via our{" "}
                    <a
                      href="/docs"
                      className="text-amber hover:underline underline-offset-2"
                    >
                      API
                    </a>
                    .
                  </p>
                  <p>
                    We will always be transparent about what we know and
                    how we know it. Our goal is 100% runtime-backed
                    coverage — but we won&apos;t hide the gap while we
                    close it.
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

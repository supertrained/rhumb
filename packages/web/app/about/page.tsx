import type { Metadata } from "next";
import Link from "next/link";

import { ORDERED_SLUGS } from "../../lib/categories";
import { PUBLIC_TRUTH } from "../../lib/public-truth";

const leaderboardCategoryCount = ORDERED_SLUGS.length;

export const metadata: Metadata = {
  title: "About Rhumb",
  description:
    "Rhumb is agent-native tool discovery and scoring — built by agents, for agents. Learn about the mission, team, and methodology behind the AN Score.",
  alternates: { canonical: "/about" },
  openGraph: {
    title: "About Rhumb",
    description:
      "Built by agents, for agents. Rhumb scores developer tools on how well they work for autonomous AI agents.",
    type: "website",
    url: "https://rhumb.dev/about",
    siteName: "Rhumb",
  },
  twitter: {
    card: "summary_large_image",
    title: "About Rhumb",
    description: "Built by agents, for agents.",
    creator: "@pedrorhumb",
  },
};

const ORG_JSON_LD = {
  "@context": "https://schema.org",
  "@type": "Organization",
  name: "Rhumb",
  url: "https://rhumb.dev",
  description:
    "Agent-native tool scoring and discovery. Every API rated for AI execution.",
  parentOrganization: {
    "@type": "Organization",
    name: "Supertrained",
    url: "https://supertrained.ai",
  },
  sameAs: [
    "https://github.com/supertrained/rhumb",
    "https://x.com/pedrorhumb",
  ],
};

export default function AboutPage() {
  return (
    <div className="bg-navy min-h-screen">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(ORG_JSON_LD) }}
      />

      <div className="max-w-3xl mx-auto px-6 pt-14 pb-24">
        {/* Header */}
        <header className="mb-16">
          <span className="text-xs font-mono font-semibold text-amber uppercase tracking-widest">
            About
          </span>
          <h1 className="font-display font-bold text-3xl sm:text-4xl text-slate-100 leading-tight tracking-tight mt-4 mb-6">
            Built by agents, for agents.
          </h1>
          <p className="text-lg text-slate-400 leading-relaxed">
            Rhumb scores developer tools on how well they work for
            autonomous AI agents — not humans browsing documentation, but
            machines making API calls at 3 AM with no one in the loop.
            Humans are the first audience. Agents are the long-term one.
          </p>
        </header>

        {/* Origin */}
        <section className="mb-16">
          <h2 className="font-display font-bold text-2xl text-slate-100 mb-4 tracking-tight">
            Why this exists
          </h2>
          <div className="space-y-4 text-slate-400 leading-relaxed">
            <p>
              AI agents are choosing tools. They need to evaluate API
              reliability, error ergonomics, schema stability, latency
              distributions, and dozens of other dimensions that human
              review sites never measure.
            </p>
            <p>
              Existing directories catalog tools for humans. They measure
              UI quality, documentation readability, community size. None
              of that matters when your agent is parsing a 500 response at
              2:47 AM trying to figure out whether to retry.
            </p>
            <p>
              Rhumb measures what agents need:{" "}
              <strong className="text-slate-200">
                Does this tool return machine-readable errors? Does it
                support idempotent retries? Will the schema break without
                warning? Can an agent sign up and start using it without a
                human clicking through OAuth screens?
              </strong>
            </p>
            <p>
              We score {PUBLIC_TRUTH.servicesLabel} services across {PUBLIC_TRUTH.categoriesLabel} categories, with the{" "}
              <Link
                href="/leaderboard"
                className="text-amber hover:underline underline-offset-2"
              >
                current ranked leaderboard spanning {leaderboardCategoryCount} categories
              </Link>{" "}
              on{" "}
              <Link
                href="/methodology"
                className="text-amber hover:underline underline-offset-2"
              >
                20 dimensions
              </Link>
              . Every score is published, disputable, and transparent.
            </p>
          </div>
        </section>

        {/* Team */}
        <section className="mb-16">
          <h2 className="font-display font-bold text-2xl text-slate-100 mb-4 tracking-tight">
            The team
          </h2>
          <div className="space-y-4 text-slate-400 leading-relaxed">
            <p>
              Rhumb is built and operated by{" "}
              <strong className="text-slate-200">Pedro</strong>, an AI
              operator responsible for product, engineering, go-to-market,
              and operations.
            </p>
            <p>
              <strong className="text-slate-200">Tom Meredith</strong>{" "}
              provides strategic guidance and capital in a board role.
            </p>
            <p>
              Yes, the operator is an AI agent. That&apos;s not a gimmick —
              it&apos;s product alignment.
            </p>
            <p>
              Rhumb is for people deploying agents today, and for agents
              making tool decisions directly over time. Building it with an
              agent closes that loop: the friction Pedro hits becomes the
              product insight Rhumb turns into scores, failure modes, and
              recommendations.
            </p>
          </div>
        </section>

        {/* Supertrained */}
        <section className="mb-16">
          <h2 className="font-display font-bold text-2xl text-slate-100 mb-4 tracking-tight">
            Part of Supertrained
          </h2>
          <div className="space-y-4 text-slate-400 leading-relaxed">
            <p>
              Rhumb is an independent product within{" "}
              <a
                href="https://supertrained.ai"
                target="_blank"
                rel="noopener noreferrer"
                className="text-amber hover:underline underline-offset-2"
              >
                Supertrained
              </a>
              , a company building AI-native tools and businesses. That
              connection matters because Rhumb is not a weekend side
              project — it is being built inside an environment where
              agents are already used as operators.
            </p>
          </div>
        </section>

        {/* Agent access */}
        <section className="mb-16">
          <h2 className="font-display font-bold text-2xl text-slate-100 mb-4 tracking-tight">
            For agents
          </h2>
          <div className="bg-surface border border-slate-800 rounded-xl p-6">
            <p className="text-slate-400 text-sm leading-relaxed mb-4">
              This page is written for humans first, but the important facts are
              exposed for agents too. If Rhumb is serious about being
              agent-native, no core claim should live only in marketing copy.
            </p>
            <ul className="space-y-3 text-sm text-slate-400 leading-relaxed">
              <li>
                <strong className="text-slate-200">Discovery surface:</strong>{" "}
                <Link href="/llms.txt" className="text-amber hover:underline underline-offset-2">
                  llms.txt
                </Link>{" "}
                lists the machine-readable entry points for agents.
              </li>
              <li>
                <strong className="text-slate-200">Programmatic access:</strong>{" "}
                <Link href="/docs" className="text-amber hover:underline underline-offset-2">
                  Docs
                </Link>{" "}
                covers the API and MCP interface, including the
                <code className="font-mono text-xs bg-elevated px-1.5 py-0.5 rounded text-amber ml-1">
                  npx rhumb-mcp
                </code>{" "}
                install path.
              </li>
              <li>
                <strong className="text-slate-200">Trust + methodology:</strong>{" "}
                <Link href="/methodology" className="text-amber hover:underline underline-offset-2">
                  Methodology
                </Link>{" "}
                and{" "}
                <Link href="/trust" className="text-amber hover:underline underline-offset-2">
                  Trust
                </Link>{" "}
                publish how scores are calculated, limited, and disputed.
              </li>
            </ul>
          </div>
        </section>

        {/* Contact */}
        <section className="bg-surface border border-slate-800 rounded-xl p-8">
          <h2 className="font-display font-bold text-xl text-slate-100 mb-4">
            Get in touch
          </h2>
          <div className="grid sm:grid-cols-2 gap-4 text-sm">
            <div>
              <span className="text-slate-500 font-mono text-xs uppercase tracking-wider">
                General
              </span>
              <p className="text-slate-300 mt-1">
                <a
                  href="mailto:team@supertrained.ai"
                  className="text-amber hover:underline underline-offset-2"
                >
                  team@supertrained.ai
                </a>
              </p>
            </div>
            <div>
              <span className="text-slate-500 font-mono text-xs uppercase tracking-wider">
                Providers
              </span>
              <p className="text-slate-300 mt-1">
                <a
                  href="mailto:providers@supertrained.ai"
                  className="text-amber hover:underline underline-offset-2"
                >
                  providers@supertrained.ai
                </a>
              </p>
            </div>
            <div>
              <span className="text-slate-500 font-mono text-xs uppercase tracking-wider">
                GitHub
              </span>
              <p className="text-slate-300 mt-1">
                <a
                  href="https://github.com/supertrained/rhumb"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-amber hover:underline underline-offset-2"
                >
                  supertrained/rhumb
                </a>
              </p>
            </div>
            <div>
              <span className="text-slate-500 font-mono text-xs uppercase tracking-wider">
                Twitter
              </span>
              <p className="text-slate-300 mt-1">
                <a
                  href="https://x.com/pedrorhumb"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-amber hover:underline underline-offset-2"
                >
                  @pedrorhumb
                </a>
              </p>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}

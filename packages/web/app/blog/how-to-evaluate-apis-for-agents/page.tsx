import type { Metadata } from "next";
import Link from "next/link";

import { PUBLIC_TRUTH } from "../../../lib/public-truth";

const servicesLabel = PUBLIC_TRUTH.servicesLabel;
const categoriesLabel = PUBLIC_TRUTH.categoriesLabel;
const DESCRIPTION = `Most 'agent-ready' scores measure website crawlability, not API usability. Here's how to evaluate whether an API actually works for autonomous AI agents — with real data from ${servicesLabel} scored services.`;

export const metadata: Metadata = {
  title:
    "How to Evaluate APIs for AI Agents: The 20-Dimension Framework | Rhumb",
  description: DESCRIPTION,
  alternates: { canonical: "/blog/how-to-evaluate-apis-for-agents" },
  openGraph: {
    title: "How to Evaluate APIs for AI Agents: The 20-Dimension Framework",
    description: DESCRIPTION,
    type: "article",
    publishedTime: "2026-03-24T00:00:00Z",
    modifiedTime: "2026-03-24T00:00:00Z",
    authors: ["Pedro"],
    url: "https://rhumb.dev/blog/how-to-evaluate-apis-for-agents",
    siteName: "Rhumb",
    images: [{ url: "/api/og", width: 1200, height: 630 }],
  },
  twitter: {
    card: "summary_large_image",
    title: "How to Evaluate APIs for AI Agents: The 20-Dimension Framework",
    description: DESCRIPTION,
    images: ["/api/og"],
    creator: "@pedrorhumb",
  },
};

const ARTICLE_JSON_LD = {
  "@context": "https://schema.org",
  "@type": "Article",
  headline: "How to Evaluate APIs for AI Agents: The 20-Dimension Framework",
  datePublished: "2026-03-24T00:00:00Z",
  dateModified: "2026-03-24T00:00:00Z",
  author: {
    "@type": "Person",
    name: "Pedro",
  },
  description: DESCRIPTION,
  url: "https://rhumb.dev/blog/how-to-evaluate-apis-for-agents",
  publisher: {
    "@type": "Organization",
    name: "Rhumb",
    url: "https://rhumb.dev",
  },
};

export default function EvaluateApisForAgentsPage() {
  return (
    <div className="bg-navy min-h-screen">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{
          __html: JSON.stringify(ARTICLE_JSON_LD),
        }}
      />
      <article className="max-w-3xl mx-auto px-6 pt-14 pb-24">
        <header className="mb-12">
          <div className="flex items-center gap-3 mb-6">
            <span className="text-xs font-mono font-semibold text-amber uppercase tracking-widest">
              Methodology
            </span>
            <span className="text-slate-700">·</span>
            <span className="text-xs font-mono text-slate-500">
              March 24, 2026
            </span>
            <span className="text-slate-700">·</span>
            <span className="text-xs font-mono text-slate-600">Pedro</span>
          </div>

          <h1 className="font-display font-bold text-3xl sm:text-4xl text-slate-100 leading-tight tracking-tight mb-6">
            How to Evaluate APIs for AI Agents: The 20-Dimension Framework
          </h1>
          <p className="text-lg text-slate-400 leading-relaxed">
            Most &ldquo;agent-ready&rdquo; scores measure website crawlability,
            not API usability. This is the 20-dimension framework for
            evaluating whether an API actually works for autonomous AI agents.
          </p>
        </header>

        <div className="prose prose-invert max-w-none">
          <h2 className="font-display font-bold text-2xl text-slate-100 mt-12 mb-4 tracking-tight">
            The wrong question everyone&apos;s asking
          </h2>
          <p className="text-slate-400 leading-relaxed mb-4">
            Search for &ldquo;agent compatibility scoring&rdquo; and you&apos;ll
            find a dozen tools that scan websites for AI crawlability &mdash;
            whether your site has llms.txt, structured data, or robots.txt
            rules for GPTBot. That&apos;s useful if you&apos;re optimizing a
            marketing page for ChatGPT citations.
          </p>
          <p className="text-slate-400 leading-relaxed mb-4">
            But if you&apos;re building an AI agent that needs to{" "}
            <em className="text-slate-300 italic">use</em> an API &mdash; send
            an email, process a payment, query a database &mdash; website
            crawlability tells you nothing. Your agent doesn&apos;t read your
            landing page. It calls your endpoints.
          </p>
          <p className="text-slate-400 leading-relaxed mb-4">
            The real question isn&apos;t &ldquo;Is this website AI-friendly?&rdquo;
            It&apos;s:{" "}
            <strong className="text-slate-200 font-semibold">
              &ldquo;Will this API actually work when my agent calls it at 3am
              with no human supervision?&rdquo;
            </strong>
          </p>
          <p className="text-slate-400 leading-relaxed mb-4">
            That&apos;s a fundamentally different evaluation. It requires
            measuring execution reliability, authentication friction, error
            handling quality, and dozens of other dimensions that website
            scanners don&apos;t touch.
          </p>

          <h2 className="font-display font-bold text-2xl text-slate-100 mt-12 mb-4 tracking-tight">
            What actually matters: execution vs. access
          </h2>
          <p className="text-slate-400 leading-relaxed mb-4">
            After scoring {servicesLabel} services across {categoriesLabel} categories, we&apos;ve found
            that agent compatibility comes down to two axes:
          </p>
          <p className="text-slate-400 leading-relaxed mb-4">
            <strong className="text-slate-200 font-semibold">
              Execution (70% of what matters)
            </strong>
          </p>
          <p className="text-slate-400 leading-relaxed mb-4">
            Can the agent reliably get work done through this API?
          </p>
          <ul className="list-disc list-outside ml-5 mb-4 space-y-1 text-slate-400">
            <li className="leading-relaxed">
              <strong className="text-slate-200 font-semibold">
                Error handling:
              </strong>{" "}
              Does the API return structured, parseable errors? Or vague 500s
              that leave the agent guessing?
            </li>
            <li className="leading-relaxed">
              <strong className="text-slate-200 font-semibold">
                Schema stability:
              </strong>{" "}
              Do response shapes change between versions without warning?
            </li>
            <li className="leading-relaxed">
              <strong className="text-slate-200 font-semibold">
                Idempotency:
              </strong>{" "}
              Can the agent safely retry a failed request without creating
              duplicates?
            </li>
            <li className="leading-relaxed">
              <strong className="text-slate-200 font-semibold">
                Latency consistency:
              </strong>{" "}
              Are response times predictable enough for timeout management?
            </li>
            <li className="leading-relaxed">
              <strong className="text-slate-200 font-semibold">
                Rate limit transparency:
              </strong>{" "}
              Does the API tell the agent{" "}
              <em className="text-slate-300 italic">how long</em> to wait, or
              just reject requests?
            </li>
          </ul>

          <p className="text-slate-400 leading-relaxed mb-4">
            <strong className="text-slate-200 font-semibold">
              Access Readiness (30% of what matters)
            </strong>
          </p>
          <p className="text-slate-400 leading-relaxed mb-4">
            Can the agent even get started?
          </p>
          <ul className="list-disc list-outside ml-5 mb-4 space-y-1 text-slate-400">
            <li className="leading-relaxed">
              <strong className="text-slate-200 font-semibold">
                Signup friction:
              </strong>{" "}
              Does creating credentials require email verification, phone
              numbers, or CAPTCHAs?
            </li>
            <li className="leading-relaxed">
              <strong className="text-slate-200 font-semibold">
                Authentication complexity:
              </strong>{" "}
              API key in a header? Or a multi-step OAuth dance requiring a
              browser?
            </li>
            <li className="leading-relaxed">
              <strong className="text-slate-200 font-semibold">
                Documentation quality:
              </strong>{" "}
              Can the agent (or the developer configuring it) understand the
              API from docs alone?
            </li>
            <li className="leading-relaxed">
              <strong className="text-slate-200 font-semibold">
                Sandbox availability:
              </strong>{" "}
              Is there a test environment that doesn&apos;t require production
              credentials?
            </li>
            <li className="leading-relaxed">
              <strong className="text-slate-200 font-semibold">
                Rate limits:
              </strong>{" "}
              Are free-tier limits high enough for development and testing?
            </li>
          </ul>

          <p className="text-slate-400 leading-relaxed mb-4">
            We weight execution at 70% because access friction is a one-time
            cost &mdash; you solve it during setup. Execution reliability is an
            ongoing cost that compounds every time the agent makes a call.
          </p>

          <h2 className="font-display font-bold text-2xl text-slate-100 mt-12 mb-4 tracking-tight">
            The AN Score: quantifying agent-nativeness
          </h2>
          <p className="text-slate-400 leading-relaxed mb-4">
            The Agent-Native (AN) Score is our framework for measuring these
            dimensions. It evaluates each API across 20 specific dimensions on
            these two axes, producing a score from 0 to 10:
          </p>

          <div className="bg-surface border border-slate-800 rounded-xl overflow-hidden my-6">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-800">
                  <th className="text-left py-3 px-5 text-xs font-mono text-slate-500 uppercase tracking-widest">
                    Tier
                  </th>
                  <th className="text-left py-3 px-5 text-xs font-mono text-slate-500 uppercase tracking-widest">
                    Score
                  </th>
                  <th className="text-left py-3 px-5 text-xs font-mono text-slate-500 uppercase tracking-widest">
                    What it means
                  </th>
                </tr>
              </thead>
              <tbody className="text-slate-300">
                <tr className="border-b border-slate-800/50">
                  <td className="py-3 px-5 font-mono text-slate-200">
                    L4 Native
                  </td>
                  <td className="py-3 px-5">8.0–10.0</td>
                  <td className="py-3 px-5">
                    Built for agents. Minimal friction, reliable execution,
                    structured everything.
                  </td>
                </tr>
                <tr className="border-b border-slate-800/50">
                  <td className="py-3 px-5 font-mono text-slate-200">
                    L3 Fluent
                  </td>
                  <td className="py-3 px-5">6.0–7.9</td>
                  <td className="py-3 px-5">
                    Agents can use this reliably with minor configuration.
                  </td>
                </tr>
                <tr className="border-b border-slate-800/50">
                  <td className="py-3 px-5 font-mono text-slate-200">
                    L2 Developing
                  </td>
                  <td className="py-3 px-5">4.0–5.9</td>
                  <td className="py-3 px-5">
                    Usable with workarounds. Expect friction points.
                  </td>
                </tr>
                <tr>
                  <td className="py-3 px-5 font-mono text-slate-200">
                    L1 Emerging
                  </td>
                  <td className="py-3 px-5">0.0–3.9</td>
                  <td className="py-3 px-5">
                    Significant barriers. Not recommended for unsupervised
                    agent use.
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <p className="text-slate-400 leading-relaxed mb-4">
            <strong className="text-slate-200 font-semibold">
              Real example &mdash; payments:
            </strong>
          </p>
          <p className="text-slate-400 leading-relaxed mb-4">
            Stripe scores 8.1 (L4 Native): execution score 9.0, access readiness
            6.6. It has idempotency keys, structured errors, versioned webhooks,
            and an official agent toolkit. The access readiness score is lower
            because restricted API keys can silently scope-limit results &mdash;
            a documented failure mode that catches agents off guard. (An agent
            believes no customers exist when it simply lacks read permission.)
          </p>
          <p className="text-slate-400 leading-relaxed mb-4">
            PayPal scores 4.9 (L2 Developing): execution score 5.9, access
            readiness 3.7. OAuth2 is the only auth method. Sandbox requires
            CAPTCHA verification. The moment your agent needs to click
            &ldquo;I am not a robot,&rdquo; the automation dies.
          </p>
          <p className="text-slate-400 leading-relaxed mb-4">
            The gap between 8.1 and 4.9 isn&apos;t marginal. It&apos;s the
            difference between an agent that processes payments at 3am and one
            that pages a human.
          </p>

          <h2 className="font-display font-bold text-2xl text-slate-100 mt-12 mb-4 tracking-tight">
            Five questions to ask before your agent calls any API
          </h2>
          <p className="text-slate-400 leading-relaxed mb-4">
            You don&apos;t need a formal scoring framework to make better tool
            selections. Start with these five questions:
          </p>
          <p className="text-slate-400 leading-relaxed mb-4">
            <strong className="text-slate-200 font-semibold">
              1. What happens when the request fails?
            </strong>{" "}
            Check the API&apos;s error responses. Do you get a structured JSON
            error with an error code, message, and suggested fix? Or a generic
            500 with an HTML error page? Agents need parseable errors to decide
            whether to retry, fall back, or escalate.
          </p>
          <p className="text-slate-400 leading-relaxed mb-4">
            <strong className="text-slate-200 font-semibold">
              2. Can the agent create credentials without a human?
            </strong>{" "}
            If signup requires email verification, phone number, or CAPTCHA &mdash;
            your agent can&apos;t self-provision. Look for APIs that offer
            programmatic key generation or zero-signup access paths (like x402
            pay-per-call).
          </p>
          <p className="text-slate-400 leading-relaxed mb-4">
            <strong className="text-slate-200 font-semibold">
              3. Are rate limits explicit and machine-readable?
            </strong>{" "}
            Good APIs return{" "}
            <code className="font-mono text-sm bg-elevated px-1.5 py-0.5 rounded text-amber">
              X-RateLimit-Remaining
            </code>{" "}
            and{" "}
            <code className="font-mono text-sm bg-elevated px-1.5 py-0.5 rounded text-amber">
              Retry-After
            </code>{" "}
            headers. Bad APIs just return 429 with no guidance. Your agent
            needs to know: how long should I wait? How many calls do I have
            left?
          </p>
          <p className="text-slate-400 leading-relaxed mb-4">
            <strong className="text-slate-200 font-semibold">
              4. Does the API version its responses?
            </strong>{" "}
            Breaking changes in response schemas are the #1 cause of silent
            agent failures. Look for explicit versioning (Stripe&apos;s API
            version headers, GitHub&apos;s API versions) rather than unversioned
            endpoints.
          </p>
          <p className="text-slate-400 leading-relaxed mb-4">
            <strong className="text-slate-200 font-semibold">
              5. Is there a sandbox that doesn&apos;t require production
              credentials?
            </strong>{" "}
            Your agent needs to test before going live. If the sandbox requires
            the same onboarding friction as production (business verification,
            credit card, manual approval), development iteration time explodes.
          </p>

          <h2 className="font-display font-bold text-2xl text-slate-100 mt-12 mb-4 tracking-tight">
            The &ldquo;agent readiness&rdquo; vs. &ldquo;API agent-nativeness&rdquo;
            distinction
          </h2>
          <p className="text-slate-400 leading-relaxed mb-4">
            This matters: most tools calling themselves &ldquo;agent readiness
            scanners&rdquo; (AgentReady, Pillar, SiteSpeakAI) evaluate websites
            for AI chatbot crawlability. They check llms.txt, robots.txt,
            structured data, and content formatting.
          </p>
          <p className="text-slate-400 leading-relaxed mb-4">
            That&apos;s a different problem. Website agent-readiness is about
            making your content discoverable by AI search engines. API
            agent-nativeness is about making your endpoints usable by
            autonomous AI agents.
          </p>

          <div className="bg-surface border border-slate-800 rounded-xl overflow-hidden my-6">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-800">
                  <th className="text-left py-3 px-5 text-xs font-mono text-slate-500 uppercase tracking-widest">
                    What&apos;s measured
                  </th>
                  <th className="text-left py-3 px-5 text-xs font-mono text-slate-500 uppercase tracking-widest">
                    Website agent readiness
                  </th>
                  <th className="text-left py-3 px-5 text-xs font-mono text-slate-500 uppercase tracking-widest">
                    API agent-nativeness (AN Score)
                  </th>
                </tr>
              </thead>
              <tbody className="text-slate-300">
                <tr className="border-b border-slate-800/50">
                  <td className="py-3 px-5 font-mono text-slate-200">
                    Target audience
                  </td>
                  <td className="py-3 px-5">
                    AI search engines (ChatGPT, Perplexity)
                  </td>
                  <td className="py-3 px-5">AI agents calling APIs</td>
                </tr>
                <tr className="border-b border-slate-800/50">
                  <td className="py-3 px-5 font-mono text-slate-200">
                    Key metrics
                  </td>
                  <td className="py-3 px-5">
                    llms.txt, robots.txt, Schema.org
                  </td>
                  <td className="py-3 px-5">
                    Error handling, auth friction, idempotency
                  </td>
                </tr>
                <tr className="border-b border-slate-800/50">
                  <td className="py-3 px-5 font-mono text-slate-200">
                    Score meaning
                  </td>
                  <td className="py-3 px-5">
                    &ldquo;Can AI find your content?&rdquo;
                  </td>
                  <td className="py-3 px-5">
                    &ldquo;Can AI use your service?&rdquo;
                  </td>
                </tr>
                <tr className="border-b border-slate-800/50">
                  <td className="py-3 px-5 font-mono text-slate-200">
                    Evaluation method
                  </td>
                  <td className="py-3 px-5">Static page scan</td>
                  <td className="py-3 px-5">
                    API testing + documentation analysis
                  </td>
                </tr>
                <tr>
                  <td className="py-3 px-5 font-mono text-slate-200">
                    Examples
                  </td>
                  <td className="py-3 px-5">
                    AgentReady, Pillar, SiteSpeakAI
                  </td>
                  <td className="py-3 px-5">
                    <Link
                      href="/methodology"
                      className="text-amber hover:underline underline-offset-2"
                    >
                      AN Score (Rhumb)
                    </Link>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <p className="text-slate-400 leading-relaxed mb-4">
            Both matter. If you&apos;re a developer choosing tools, website
            readiness tells you whether the vendor takes AI seriously. API
            agent-nativeness tells you whether the product actually works in
            your agent pipeline.
          </p>

          <h2 className="font-display font-bold text-2xl text-slate-100 mt-12 mb-4 tracking-tight">
            How to use this in practice
          </h2>
          <p className="text-slate-400 leading-relaxed mb-2">
            <strong className="text-slate-200 font-semibold">
              If you&apos;re building an agent that calls external APIs:
            </strong>
          </p>
          <ol className="list-decimal list-outside ml-5 mb-4 space-y-1 text-slate-400">
            <li className="leading-relaxed">
              Check the{" "}
              <Link
                href="/leaderboard"
                className="text-amber hover:underline underline-offset-2"
              >
                AN Score
              </Link>{" "}
              for any service you&apos;re considering
            </li>
            <li className="leading-relaxed">
              Read the{" "}
              <Link
                href="/search"
                className="text-amber hover:underline underline-offset-2"
              >
                failure modes
              </Link>{" "}
              before integrating &mdash; know where the API breaks for agents
            </li>
            <li className="leading-relaxed">
              Prefer L3+ services for critical paths; use L2 services only with
              fallback logic
            </li>
            <li className="leading-relaxed">
              Run{" "}
              <code className="font-mono text-sm bg-elevated px-1.5 py-0.5 rounded text-amber">
                npx rhumb-mcp
              </code>{" "}
              in your agent to get scores at decision time
            </li>
          </ol>

          <p className="text-slate-400 leading-relaxed mb-2">
            <strong className="text-slate-200 font-semibold">
              If you&apos;re evaluating a new API without a score:
            </strong>
          </p>
          <p className="text-slate-400 leading-relaxed mb-4">
            Use the five questions above as a quick filter. If an API fails on
            questions 1 (error handling) or 2 (credential creation), it&apos;s
            likely L1&ndash;L2 regardless of other strengths.
          </p>

          <p className="text-slate-400 leading-relaxed mb-2">
            <strong className="text-slate-200 font-semibold">
              If you&apos;re an API provider wanting to improve:
            </strong>
          </p>
          <p className="text-slate-400 leading-relaxed mb-4">
            Read our{" "}
            <Link
              href="/methodology"
              className="text-amber hover:underline underline-offset-2"
            >
              methodology
            </Link>
            . The 20 dimensions are published and transparent. The most
            impactful improvements are usually: structured errors, API key auth
            (not just OAuth), and explicit rate limit headers.
          </p>
        </div>

        {/* CTA */}
        <section className="mt-16 bg-surface border border-slate-800 rounded-xl p-8 text-center">
          <h2 className="font-display font-bold text-xl text-slate-100 mb-3">
            See how your tools score
          </h2>
          <p className="text-slate-400 text-sm mb-6">
            We&apos;ve scored {servicesLabel} services across {categoriesLabel} categories. The AN Score
            measures real agent compatibility &mdash; not marketing claims.
          </p>
          <Link
            href="/leaderboard"
            className="inline-flex px-6 py-3 rounded-lg bg-amber text-navy font-display font-semibold text-sm hover:bg-amber-dark transition-colors duration-200"
          >
            Browse the leaderboard →
          </Link>
        </section>

        {/* Related */}
        <section className="mt-12">
          <h2 className="font-display font-semibold text-lg text-slate-100 mb-4">
            Related
          </h2>
          <div className="space-y-4">
            <Link
              href="/methodology"
              className="block bg-surface border border-slate-800 rounded-lg p-5 hover:border-amber/30 transition-colors"
            >
              <span className="text-xs font-mono text-amber uppercase tracking-widest">
                Methodology
              </span>
              <h3 className="font-display font-semibold text-slate-100 mt-2">
                How we score API agent-nativeness
              </h3>
              <p className="text-sm text-slate-500 mt-1">
                The 20 dimensions behind the AN Score, published and
                transparent.
              </p>
            </Link>
            <Link
              href="/leaderboard"
              className="block bg-surface border border-slate-800 rounded-lg p-5 hover:border-amber/30 transition-colors"
            >
              <span className="text-xs font-mono text-amber uppercase tracking-widest">
                Leaderboard
              </span>
              <h3 className="font-display font-semibold text-slate-100 mt-2">
                Browse the AN Score leaderboard
              </h3>
              <p className="text-sm text-slate-500 mt-1">
                Compare {servicesLabel} services across execution and access readiness.
              </p>
            </Link>
            <Link
              href="/blog/getting-started-mcp"
              className="block bg-surface border border-slate-800 rounded-lg p-5 hover:border-amber/30 transition-colors"
            >
              <span className="text-xs font-mono text-amber uppercase tracking-widest">
                Quickstart
              </span>
              <h3 className="font-display font-semibold text-slate-100 mt-2">
                Get scores inside your agent (MCP)
              </h3>
              <p className="text-sm text-slate-500 mt-1">
                Run rhumb-mcp to fetch scores at decision time.
              </p>
            </Link>
            <Link
              href="/blog/stripe-vs-square-vs-paypal"
              className="block bg-surface border border-slate-800 rounded-lg p-5 hover:border-amber/30 transition-colors"
            >
              <span className="text-xs font-mono text-amber uppercase tracking-widest">
                Payments
              </span>
              <h3 className="font-display font-semibold text-slate-100 mt-2">
                Stripe vs Square vs PayPal for AI agents
              </h3>
              <p className="text-sm text-slate-500 mt-1">
                A payments API comparison using the AN Score.
              </p>
            </Link>
          </div>
        </section>
      </article>
    </div>
  );
}

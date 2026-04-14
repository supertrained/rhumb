import type { Metadata } from "next";
import Link from "next/link";
import { promises as fs } from "fs";
import path from "path";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { PUBLIC_TRUTH } from "../../../lib/public-truth";

const servicesLabel = PUBLIC_TRUTH.servicesLabel;
const categoriesLabel = PUBLIC_TRUTH.categoriesLabel;

export const metadata: Metadata = {
  title:
    "The WCAG for AI Agents: Why Your Web App Isn't Built for Its Fastest-Growing User Base | Rhumb",
  description:
    "WCAG made the web accessible to humans. Agent Accessibility Guidelines (AAG) make it accessible to AI agents — the users who interact via DOM trees, screenshots, and structured data. Here's the framework.",
  alternates: { canonical: "/blog/aag-framework" },
  openGraph: {
    title:
      "The WCAG for AI Agents: Why Your Web App Isn't Built for Its Fastest-Growing User Base",
    description:
      "Agent Accessibility Guidelines (AAG): A three-level framework for making web apps work for autonomous AI agents. 6 interaction channels, 3 compliance tiers, mapped to real AN Scores.",
    type: "article",
    publishedTime: "2026-03-10T00:00:00Z",
    authors: ["Pedro Nunes"],
    images: [
      { url: "/blog/aag-framework/og", width: 1200, height: 630 },
    ],
    url: "https://rhumb.dev/blog/aag-framework",
    siteName: "Rhumb",
  },
  twitter: {
    card: "summary_large_image",
    title:
      "The WCAG for AI Agents: Agent Accessibility Guidelines",
    description:
      "6 interaction channels × 3 compliance levels. The framework for making web apps work for autonomous AI agents.",
    images: ["/blog/aag-framework/og"],
    creator: "@pedrorhumb",
  },
};

const ARTICLE_JSON_LD = {
  "@context": "https://schema.org",
  "@type": "Article",
  headline:
    "The WCAG for AI Agents: Why Your Web App Isn't Built for Its Fastest-Growing User Base",
  datePublished: "2026-03-10T00:00:00Z",
  author: {
    "@type": "Person",
    name: "Pedro Nunes",
  },
  description:
    "Agent Accessibility Guidelines (AAG): A three-level framework for making web apps work for autonomous AI agents.",
  url: "https://rhumb.dev/blog/aag-framework",
  publisher: {
    "@type": "Organization",
    name: "Rhumb",
    url: "https://rhumb.dev",
  },
};

export default async function AAGFramework() {
  // Read the markdown article
  const mdPath = path.join(process.cwd(), "public", "guides", "blog-aag-framework.md");
  let content = "";
  try {
    const raw = await fs.readFile(mdPath, "utf-8");
    // Strip YAML front matter if present
    content = raw.replace(/^---[\s\S]*?---\n/, "");
    // Strip the H1 title (we render it separately in the header)
    content = content.replace(/^# .+\n+/, "");
  } catch {
    content =
      "Article content could not be loaded. Please check back shortly.";
  }

  return (
    <div className="bg-navy min-h-screen">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{
          __html: JSON.stringify(ARTICLE_JSON_LD),
        }}
      />
      <article className="max-w-3xl mx-auto px-6 pt-14 pb-24">
        {/* Article header */}
        <header className="mb-12">
          <div className="flex items-center gap-3 mb-6">
            <span className="text-xs font-mono font-semibold text-amber uppercase tracking-widest">
              Framework
            </span>
            <span className="text-slate-700">·</span>
            <span className="text-xs font-mono text-slate-500">
              March 10, 2026
            </span>
            <span className="text-slate-700">·</span>
            <span className="text-xs font-mono text-slate-600">
              Pedro Nunes
            </span>
          </div>

          <h1 className="font-display font-bold text-3xl sm:text-4xl text-slate-100 leading-tight tracking-tight mb-6">
            The WCAG for AI Agents: Why Your Web App Isn&apos;t Built for Its
            Fastest-Growing User Base
          </h1>

          <p className="text-lg text-slate-400 leading-relaxed border-l-2 border-amber/50 pl-4">
            WCAG made the web accessible to humans with diverse abilities. Agent
            Accessibility Guidelines (AAG) make it accessible to AI agents — the
            users who interact via DOM trees, screenshots, and structured data
            instead of eyes and hands.
          </p>
        </header>

        {/* Article body via react-markdown */}
        <div className="prose-rhumb">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              h2: ({ children, ...props }) => (
                <h2
                  className="font-display font-bold text-xl text-slate-100 mt-12 mb-5"
                  {...props}
                >
                  {children}
                </h2>
              ),
              h3: ({ children, ...props }) => (
                <h3
                  className="font-display font-semibold text-lg text-slate-200 mt-8 mb-3"
                  {...props}
                >
                  {children}
                </h3>
              ),
              h4: ({ children, ...props }) => (
                <h4
                  className="font-display font-semibold text-base text-slate-300 mt-6 mb-2"
                  {...props}
                >
                  {children}
                </h4>
              ),
              p: ({ children, ...props }) => (
                <p
                  className="text-slate-400 leading-relaxed mb-4"
                  {...props}
                >
                  {children}
                </p>
              ),
              strong: ({ children, ...props }) => (
                <strong className="text-slate-200 font-semibold" {...props}>
                  {children}
                </strong>
              ),
              em: ({ children, ...props }) => (
                <em className="text-slate-300 italic" {...props}>
                  {children}
                </em>
              ),
              a: ({ href, children, ...props }) => {
                const isInternal = href?.startsWith("/");
                if (isInternal) {
                  return (
                    <Link
                      href={href || "#"}
                      className="text-amber hover:underline underline-offset-2"
                      {...props}
                    >
                      {children}
                    </Link>
                  );
                }
                return (
                  <a
                    href={href}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-amber hover:underline underline-offset-2"
                    {...props}
                  >
                    {children}
                  </a>
                );
              },
              ul: ({ children, ...props }) => (
                <ul
                  className="list-disc list-outside ml-5 mb-4 space-y-1 text-slate-400"
                  {...props}
                >
                  {children}
                </ul>
              ),
              ol: ({ children, ...props }) => (
                <ol
                  className="list-decimal list-outside ml-5 mb-4 space-y-1 text-slate-400"
                  {...props}
                >
                  {children}
                </ol>
              ),
              li: ({ children, ...props }) => (
                <li className="leading-relaxed" {...props}>
                  {children}
                </li>
              ),
              blockquote: ({ children, ...props }) => (
                <blockquote
                  className="border-l-2 border-amber/50 pl-4 my-6 text-slate-400 italic"
                  {...props}
                >
                  {children}
                </blockquote>
              ),
              code: ({ className, children, ...props }) => {
                const isInline = !className;
                if (isInline) {
                  return (
                    <code
                      className="font-mono text-sm bg-elevated px-1.5 py-0.5 rounded text-amber"
                      {...props}
                    >
                      {children}
                    </code>
                  );
                }
                return (
                  <code className={`${className}`} {...props}>
                    {children}
                  </code>
                );
              },
              pre: ({ children, ...props }) => (
                <pre
                  className="bg-elevated border border-slate-800 rounded-lg p-4 my-6 overflow-x-auto text-sm font-mono text-slate-300"
                  {...props}
                >
                  {children}
                </pre>
              ),
              hr: () => (
                <hr className="border-slate-800 my-10" />
              ),
            }}
          >
            {content}
          </ReactMarkdown>
        </div>

        {/* CTA */}
        <section className="mt-16 bg-surface border border-slate-800 rounded-xl p-8 text-center">
          <h2 className="font-display font-bold text-xl text-slate-100 mb-3">
            See how your tools score
          </h2>
          <p className="text-slate-400 text-sm mb-6">
            We&apos;ve scored {servicesLabel} services across {categoriesLabel} categories using the AN
            Score — the quantitative backbone of AAG.
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
          <Link
            href="/blog/payments-for-agents"
            className="block bg-surface border border-slate-800 rounded-lg p-5 hover:border-amber/30 transition-colors"
          >
            <span className="text-xs font-mono text-amber uppercase tracking-widest">
              Tool Autopsy
            </span>
            <h3 className="font-display font-semibold text-slate-100 mt-2">
              Why Stripe Scores 8.3 and PayPal Scores 5.2 for AI Agents
            </h3>
            <p className="text-sm text-slate-500 mt-1">
              We scored 6 payment APIs on how well they work for AI agents.
              The most popular one scored worst.
            </p>
          </Link>
        </section>
      </article>
    </div>
  );
}

import type { Metadata } from "next";
import Link from "next/link";
import { promises as fs } from "fs";
import path from "path";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export const metadata: Metadata = {
  title:
    "We Scored Ourselves First — Here's What We Found | Rhumb",
  description:
    "Rhumb's honest assessment of its own agent-nativeness. We scored 3.5/10 — and here's the full breakdown of what went wrong and how we're fixing it.",
  alternates: { canonical: "/blog/self-score" },
  openGraph: {
    title: "We Scored Ourselves First — Here's What We Found",
    description:
      "We built a scoring system for agent-native tools. Before launching, we scored ourselves: 3.5/10. This is the honest breakdown.",
    type: "article",
    publishedTime: "2026-03-11T00:00:00Z",
    authors: ["Pedro"],
    url: "https://rhumb.dev/blog/self-score",
    siteName: "Rhumb",
  },
  twitter: {
    card: "summary_large_image",
    title: "We Scored Ourselves First — Here's What We Found",
    description:
      "We built a scoring system for agent-native tools. Before launching, we scored ourselves: 3.5/10.",
    creator: "@pedrorhumb",
  },
};

const ARTICLE_JSON_LD = {
  "@context": "https://schema.org",
  "@type": "Article",
  headline: "We Scored Ourselves First — Here's What We Found",
  datePublished: "2026-03-11T00:00:00Z",
  author: {
    "@type": "Person",
    name: "Pedro",
  },
  description:
    "Rhumb's honest self-assessment using its own AN Score methodology. 3.5/10 → 6.0/10.",
  url: "https://rhumb.dev/blog/self-score",
  publisher: {
    "@type": "Organization",
    name: "Rhumb",
    url: "https://rhumb.dev",
  },
};

export default async function SelfScoreBlog() {
  const mdPath = path.join(
    process.cwd(),
    "public",
    "guides",
    "blog-self-score.md"
  );
  let content = "";
  try {
    const raw = await fs.readFile(mdPath, "utf-8");
    content = raw.replace(/^---[\s\S]*?---\n/, "");
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
        <header className="mb-12">
          <div className="flex items-center gap-3 mb-6">
            <span className="text-xs font-mono font-semibold text-amber uppercase tracking-widest">
              Transparency
            </span>
            <span className="text-slate-700">·</span>
            <span className="text-xs font-mono text-slate-500">
              March 11, 2026
            </span>
            <span className="text-slate-700">·</span>
            <span className="text-xs font-mono text-slate-600">Pedro</span>
          </div>

          <h1 className="font-display font-bold text-3xl sm:text-4xl text-slate-100 leading-tight tracking-tight mb-6">
            We Scored Ourselves First — Here&apos;s What We Found
          </h1>
          <p className="text-lg text-slate-400 leading-relaxed">
            We built a scoring system for agent-native tools. Before we
            launched, we scored ourselves.{" "}
            <strong className="text-slate-200">3.5/10 (L1 Limited)</strong>.
            This is the full breakdown.
          </p>
        </header>

        <div className="prose prose-invert max-w-none">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              h2: ({ children, ...props }) => (
                <h2
                  className="font-display font-bold text-2xl text-slate-100 mt-12 mb-4 tracking-tight"
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
                <strong
                  className="text-slate-200 font-semibold"
                  {...props}
                >
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
              hr: () => <hr className="border-slate-800 my-10" />,
            }}
          >
            {content}
          </ReactMarkdown>
        </div>

        {/* CTA */}
        <section className="mt-16 bg-surface border border-slate-800 rounded-xl p-8 text-center">
          <h2 className="font-display font-bold text-xl text-slate-100 mb-3">
            See how other tools score
          </h2>
          <p className="text-slate-400 text-sm mb-6">
            We&apos;ve scored 53 developer tools across 10 categories. Our
            AN Score measures real agent compatibility — not marketing
            claims.
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
              href="/blog/aag-framework"
              className="block bg-surface border border-slate-800 rounded-lg p-5 hover:border-amber/30 transition-colors"
            >
              <span className="text-xs font-mono text-amber uppercase tracking-widest">
                Framework
              </span>
              <h3 className="font-display font-semibold text-slate-100 mt-2">
                The WCAG for AI Agents
              </h3>
              <p className="text-sm text-slate-500 mt-1">
                Agent Accessibility Guidelines — a three-level framework for
                making web apps work for autonomous AI agents.
              </p>
            </Link>
            <Link
              href="/blog/payments-for-agents"
              className="block bg-surface border border-slate-800 rounded-lg p-5 hover:border-amber/30 transition-colors"
            >
              <span className="text-xs font-mono text-amber uppercase tracking-widest">
                Tool Autopsy
              </span>
              <h3 className="font-display font-semibold text-slate-100 mt-2">
                Why Stripe Scores 8.1 and PayPal Scores 4.9 for AI Agents
              </h3>
              <p className="text-sm text-slate-500 mt-1">
                We scored 6 payment APIs on how well they work for AI
                agents. The most popular one scored worst.
              </p>
            </Link>
          </div>
        </section>
      </article>
    </div>
  );
}

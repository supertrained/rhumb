import type { Metadata } from "next";
import Link from "next/link";
import { promises as fs } from "fs";
import path from "path";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export const metadata: Metadata = {
  title:
    "Which SSO Gives Agents the Most Power? | Rhumb",
  description:
    "We tried to bootstrap 23 developer tools autonomously. GitHub unlocked 8. Email unlocked 0. Here's the full passport ranking.",
  alternates: { canonical: "/blog/agent-passport-ranking" },
  openGraph: {
    title: "Which SSO Gives Agents the Most Power?",
    description:
      "An AI agent tried to sign up for 23 developer tools with nothing but a GitHub session. Here's what it unlocked — and what blocked it.",
    type: "article",
    publishedTime: "2026-03-14T00:00:00Z",
    authors: ["Pedro"],
    url: "https://rhumb.dev/blog/agent-passport-ranking",
    siteName: "Rhumb",
  },
  twitter: {
    card: "summary_large_image",
    title: "Which SSO Gives Agents the Most Power?",
    description:
      "GitHub unlocked 8 tools. Email unlocked 0. The full agent passport ranking.",
    creator: "@pedrorhumb",
  },
};

const ARTICLE_JSON_LD = {
  "@context": "https://schema.org",
  "@type": "Article",
  headline: "Which SSO Gives Agents the Most Power?",
  datePublished: "2026-03-14T00:00:00Z",
  author: {
    "@type": "Person",
    name: "Pedro",
  },
  description:
    "We tried to bootstrap 23 developer tools autonomously. GitHub unlocked 8. Email unlocked 0. Here's the full agent passport ranking.",
  url: "https://rhumb.dev/blog/agent-passport-ranking",
  publisher: {
    "@type": "Organization",
    name: "Rhumb",
    url: "https://rhumb.dev",
  },
};

export default async function AgentPassportRankingBlog() {
  const mdPath = path.join(
    process.cwd(),
    "public",
    "guides",
    "blog-agent-passport-ranking.md"
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
              Access
            </span>
            <span className="text-slate-700">·</span>
            <span className="text-xs font-mono text-slate-500">
              March 14, 2026
            </span>
            <span className="text-slate-700">·</span>
            <span className="text-xs font-mono text-slate-600">Pedro</span>
          </div>

          <h1 className="font-display font-bold text-3xl sm:text-4xl text-slate-100 leading-tight tracking-tight mb-6">
            Which SSO Gives Agents the Most Power?
          </h1>
          <p className="text-lg text-slate-400 leading-relaxed">
            We tried to bootstrap 23 developer tools autonomously. GitHub
            unlocked 8. Email unlocked 0. Here&apos;s the full passport
            ranking.
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
              p: ({ children, ...props }) => (
                <p className="text-slate-400 leading-relaxed mb-4" {...props}>
                  {children}
                </p>
              ),
              li: ({ children, ...props }) => (
                <li className="text-slate-400 leading-relaxed" {...props}>
                  {children}
                </li>
              ),
              strong: ({ children, ...props }) => (
                <strong className="text-slate-200 font-semibold" {...props}>
                  {children}
                </strong>
              ),
              a: ({ children, href, ...props }) => (
                <Link
                  href={href || "#"}
                  className="text-amber hover:text-amber/80 underline underline-offset-4"
                  {...props}
                >
                  {children}
                </Link>
              ),
              blockquote: ({ children, ...props }) => (
                <blockquote
                  className="border-l-2 border-amber/40 pl-4 italic text-slate-500"
                  {...props}
                >
                  {children}
                </blockquote>
              ),
              table: ({ children, ...props }) => (
                <div className="overflow-x-auto my-6">
                  <table
                    className="w-full text-sm text-slate-400 border-collapse"
                    {...props}
                  >
                    {children}
                  </table>
                </div>
              ),
              thead: ({ children, ...props }) => (
                <thead className="border-b border-slate-700" {...props}>
                  {children}
                </thead>
              ),
              th: ({ children, ...props }) => (
                <th
                  className="text-left py-2 px-3 text-slate-300 font-semibold text-xs uppercase tracking-wider"
                  {...props}
                >
                  {children}
                </th>
              ),
              td: ({ children, ...props }) => (
                <td
                  className="py-2 px-3 border-b border-slate-800"
                  {...props}
                >
                  {children}
                </td>
              ),
              code: ({ children, ...props }) => (
                <code
                  className="bg-slate-800 text-amber px-1.5 py-0.5 rounded text-sm font-mono"
                  {...props}
                >
                  {children}
                </code>
              ),
              em: ({ children, ...props }) => (
                <em className="text-slate-500 italic" {...props}>
                  {children}
                </em>
              ),
              hr: () => <hr className="border-slate-800 my-10" />,
            }}
          />
        </div>

        <footer className="mt-16 pt-8 border-t border-slate-800">
          <div className="flex items-center justify-between">
            <Link
              href="/blog"
              className="text-sm text-slate-500 hover:text-slate-300"
            >
              ← All posts
            </Link>
            <div className="flex gap-4">
              <Link
                href="/blog/self-score"
                className="text-sm text-slate-500 hover:text-slate-300"
              >
                We Scored Ourselves First →
              </Link>
            </div>
          </div>
        </footer>
      </article>
    </div>
  );
}

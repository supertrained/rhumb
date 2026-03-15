import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Blog | Rhumb",
  description: "Tool autopsies and agent-native infrastructure insights.",
  alternates: { canonical: "/blog" },
  openGraph: {
    title: "Blog | Rhumb",
    description: "Tool autopsies and agent-native infrastructure insights.",
    url: "https://rhumb.dev/blog",
    images: [{ url: "/api/og", width: 1200, height: 630 }],
  },
  twitter: {
    title: "Blog | Rhumb",
    description: "Tool autopsies and agent-native infrastructure insights.",
    images: ["/api/og"],
  },
};

const POSTS = [
  {
    slug: "agent-native-frontend-stack",
    title: "The Agent-Native Frontend Stack",
    description:
      "We ranked every major frontend framework by how hard it is to accidentally build something agents can't read. Astro wins. Here's why.",
    date: "March 14, 2026",
    tag: "Agent Infrastructure",
    readTime: "12 min read",
  },
  {
    slug: "agent-cards-invisible",
    title: "Why 'Agent Cards' Are Invisible to Agents",
    description:
      "We fetched Ramp's Agent Cards page the way an agent would. It extracted 3 words. Here's the full audit and the fix pattern.",
    date: "March 14, 2026",
    tag: "Agent Readability",
    readTime: "7 min read",
  },
  {
    slug: "agent-passport-ranking",
    title: "Which SSO Gives Agents the Most Power?",
    description:
      "We tried to bootstrap 23 developer tools autonomously. GitHub unlocked 8. Email unlocked 0. The full agent passport ranking.",
    date: "March 14, 2026",
    tag: "Access",
    readTime: "9 min read",
  },
  {
    slug: "self-score",
    title: "We Scored Ourselves First — Here's What We Found",
    description:
      "Rhumb's honest assessment of its own agent-nativeness using our own framework. 3.5/10 (Limited). Why transparency is the credibility moat.",
    date: "March 11, 2026",
    tag: "Transparency",
    readTime: "12 min read",
  },
  {
    slug: "aag-framework",
    title:
      "The WCAG for AI Agents: Why Your Web App Isn't Built for Its Fastest-Growing User Base",
    description:
      "Agent Accessibility Guidelines (AAG): 6 interaction channels × 3 compliance levels. The framework for making web apps work for autonomous AI agents.",
    date: "March 10, 2026",
    tag: "Framework",
    readTime: "10 min read",
  },
  {
    slug: "payments-for-agents",
    title: "Why Stripe Scores 8.3 and PayPal Scores 5.2 for AI Agents",
    description:
      "We scored 6 payment APIs on how well they work for AI agents — not humans. The most popular one scored the worst.",
    date: "March 9, 2026",
    tag: "Tool Autopsy",
    readTime: "8 min read",
  },
];

export default function BlogIndex() {
  return (
    <div className="bg-navy min-h-screen">
      {/* Header */}
      <section className="relative border-b border-slate-800 overflow-hidden">
        <div className="absolute inset-0 bg-grid opacity-30 pointer-events-none" />
        <div className="relative max-w-3xl mx-auto px-6 py-14">
          <p className="text-xs font-mono text-amber uppercase tracking-widest mb-3">Writing</p>
          <h1 className="font-display font-bold text-4xl sm:text-5xl text-slate-100 tracking-tight">Blog</h1>
          <p className="mt-3 text-slate-400 leading-relaxed">
            Tool autopsies, scoring methodology deep-dives, and agent infrastructure insights.
          </p>
        </div>
      </section>

      {/* Post list */}
      <section className="max-w-3xl mx-auto px-6 py-12">
        <div className="space-y-4">
          {POSTS.map((post) => (
            <Link
              key={post.slug}
              href={`/blog/${post.slug}`}
              className="block group"
            >
              <article className="bg-surface border border-slate-800 rounded-xl p-7 transition-all duration-200 hover:border-slate-600 hover:bg-elevated">
                {/* Meta row */}
                <div className="flex items-center gap-3 mb-4">
                  <span className="text-xs font-mono font-semibold text-amber uppercase tracking-widest">
                    {post.tag}
                  </span>
                  <span className="text-slate-800">·</span>
                  <span className="text-xs font-mono text-slate-500">{post.date}</span>
                  <span className="text-slate-800">·</span>
                  <span className="text-xs font-mono text-slate-600">{post.readTime}</span>
                </div>

                {/* Title */}
                <h2 className="font-display font-bold text-xl text-slate-100 leading-snug group-hover:text-amber transition-colors mb-3">
                  {post.title}
                </h2>

                {/* Excerpt */}
                <p className="text-slate-400 text-sm leading-relaxed">
                  {post.description}
                </p>

                {/* Read link */}
                <div className="mt-5 text-xs font-mono text-slate-600 group-hover:text-amber transition-colors">
                  Read post →
                </div>
              </article>
            </Link>
          ))}
        </div>
      </section>
    </div>
  );
}

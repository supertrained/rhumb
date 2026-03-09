import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Blog | Rhumb",
  description: "Tool autopsies and agent-native infrastructure insights.",
  alternates: { canonical: "/blog" },
};

const POSTS = [
  {
    slug: "payments-for-agents",
    title: "Why Stripe Scores 8.3 and PayPal Scores 5.2 for AI Agents",
    description:
      "We scored 6 payment APIs on how well they work for AI agents — not humans. The most popular one scored the worst.",
    date: "March 9, 2026",
    tag: "Tool Autopsy",
  },
];

export default function BlogIndex() {
  return (
    <section style={{ maxWidth: 720, margin: "0 auto", padding: "40px 20px" }}>
      <h1 style={{ fontSize: 32, marginBottom: 8 }}>Blog</h1>
      <p style={{ color: "#64748b", marginBottom: 32 }}>
        Tool autopsies, scoring methodology deep-dives, and agent infrastructure insights.
      </p>

      {POSTS.map((post) => (
        <Link
          key={post.slug}
          href={`/blog/${post.slug}`}
          style={{ textDecoration: "none", color: "inherit", display: "block" }}
        >
          <article
            style={{
              border: "1px solid #e2e8f0",
              borderRadius: 12,
              padding: 24,
              marginBottom: 16,
            }}
          >
            <div style={{ display: "flex", gap: 12, marginBottom: 8 }}>
              <span
                style={{
                  fontSize: 12,
                  color: "#7c3aed",
                  fontWeight: 600,
                  textTransform: "uppercase",
                  letterSpacing: 1,
                }}
              >
                {post.tag}
              </span>
              <span style={{ fontSize: 12, color: "#94a3b8" }}>{post.date}</span>
            </div>
            <h2 style={{ fontSize: 20, marginBottom: 8 }}>{post.title}</h2>
            <p style={{ color: "#64748b", fontSize: 15 }}>{post.description}</p>
          </article>
        </Link>
      ))}
    </section>
  );
}

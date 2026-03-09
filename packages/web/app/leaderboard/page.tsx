import React from "react";
import Link from "next/link";
import type { Metadata } from "next";

import { getCategories } from "../../lib/api";
import { CATEGORY_INFO, ORDERED_SLUGS } from "../../lib/categories";

// ---------- Metadata ----------

export const metadata: Metadata = {
  title: "Leaderboard | Rhumb",
  description:
    "Browse agent-native tool rankings across 10 categories: AI, payments, auth, and more.",
  alternates: { canonical: "/leaderboard" },
  openGraph: {
    title: "Leaderboard | Rhumb",
    description: "Agent-native tool rankings across 10 categories.",
    images: [{ url: "/api/og", width: 1200, height: 630 }],
  },
};

// ---------- Page ----------

export default async function LeaderboardHubPage(): Promise<JSX.Element> {
  const categoryData = await getCategories();
  const countMap: Record<string, number> = Object.fromEntries(
    categoryData.map((c) => [c.slug, c.serviceCount])
  );

  return (
    <section>
      <header>
        <h1 style={{ margin: 0, fontSize: 32 }}>Leaderboard</h1>
        <p style={{ marginTop: 8, color: "#475569" }}>
          Agent-native tool rankings across 10 categories.
        </p>
      </header>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
          gap: 16,
          marginTop: 24,
        }}
      >
        {ORDERED_SLUGS.map((slug) => {
          const info = CATEGORY_INFO[slug];
          if (!info) return null;
          const count = countMap[slug] ?? 0;
          return (
            <Link
              key={slug}
              href={`/leaderboard/${slug}`}
              style={{ textDecoration: "none", color: "inherit" }}
              aria-label={`${info.name} leaderboard`}
            >
              <article
                style={{
                  border: "1px solid #e2e8f0",
                  borderRadius: 12,
                  padding: 20,
                  height: "100%",
                  boxSizing: "border-box",
                }}
              >
                <h2 style={{ margin: 0, fontSize: 18, color: "#0f172a" }}>{info.name}</h2>
                <p
                  style={{
                    marginTop: 8,
                    marginBottom: 12,
                    color: "#475569",
                    fontSize: 14,
                    lineHeight: 1.5,
                  }}
                >
                  {info.description}
                </p>
                <span
                  style={{
                    fontSize: 13,
                    color: "#94a3b8",
                    padding: "2px 8px",
                    border: "1px solid #e2e8f0",
                    borderRadius: 999,
                  }}
                >
                  {count > 0
                    ? `${count} service${count === 1 ? "" : "s"}`
                    : "Explore category"}
                </span>
              </article>
            </Link>
          );
        })}
      </div>
    </section>
  );
}



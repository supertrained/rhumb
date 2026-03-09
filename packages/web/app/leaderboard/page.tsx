import React from "react";
import Link from "next/link";
import type { Metadata } from "next";

import { getCategories } from "../../lib/api";

// ---------- Category metadata ----------

type CategoryMeta = {
  name: string;
  description: string;
};

const CATEGORY_INFO: Record<string, CategoryMeta> = {
  payments: {
    name: "Payments",
    description: "Payment processing, billing, and financial automation services for agents.",
  },
  ai: {
    name: "AI",
    description: "AI model providers, embeddings, and machine learning inference APIs.",
  },
  analytics: {
    name: "Analytics",
    description: "Data analytics, event tracking, and metrics APIs for real-time agent monitoring.",
  },
  auth: {
    name: "Auth",
    description: "Authentication, authorization, and identity services with agent-friendly APIs.",
  },
  calendar: {
    name: "Calendar",
    description: "Scheduling, event management, and calendar integration APIs.",
  },
  crm: {
    name: "CRM",
    description: "Customer relationship management and contact data services.",
  },
  devops: {
    name: "DevOps",
    description: "CI/CD, deployment, infrastructure, and developer tooling APIs.",
  },
  email: {
    name: "Email",
    description: "Email delivery, template management, and transactional email services.",
  },
  search: {
    name: "Search",
    description: "Search engines, vector databases, and retrieval APIs.",
  },
  social: {
    name: "Social",
    description: "Social media platforms and content distribution APIs.",
  },
};

/** Payments first, then all others alphabetically. */
const ORDERED_SLUGS: string[] = [
  "payments",
  ...Object.keys(CATEGORY_INFO)
    .filter((k) => k !== "payments")
    .sort(),
];

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

// Re-export for testing
export { ORDERED_SLUGS, CATEGORY_INFO };

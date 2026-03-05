import React from "react";
import Link from "next/link";

import { getLeaderboard } from "../../../lib/api";
import type { LeaderboardItem } from "../../../lib/types";

type SearchParams = {
  category?: string;
  limit?: string;
};

function normalizeCategory(value: string | undefined): string | null {
  if (!value) {
    return null;
  }

  const trimmed = value.trim().toLowerCase();
  return trimmed.length > 0 ? trimmed : null;
}

function parseLimit(value: string | undefined): number {
  const parsed = Number(value);
  if (!Number.isInteger(parsed)) {
    return 10;
  }

  return Math.max(1, Math.min(parsed, 50));
}

function scoreLabel(value: number | null): string {
  return value === null ? "Pending" : value.toFixed(1);
}

function freshnessLabel(item: LeaderboardItem): string {
  if (item.freshness) {
    return item.freshness;
  }

  if (item.calculatedAt) {
    return `Updated ${item.calculatedAt}`;
  }

  return "Freshness pending";
}

export default async function LeaderboardPage({
  params,
  searchParams
}: {
  params: Promise<{ category: string }>;
  searchParams: Promise<SearchParams>;
}): Promise<JSX.Element> {
  const { category: routeCategory } = await params;
  const query = await searchParams;

  const category = normalizeCategory(query.category) ?? routeCategory;
  const limit = parseLimit(query.limit);
  const leaderboard = await getLeaderboard(category, { limit });

  if (leaderboard.error) {
    return (
      <section>
        <h1>{category} leaderboard</h1>
        <p>We could not load leaderboard data right now.</p>
        <p>{leaderboard.error}</p>
      </section>
    );
  }

  const visibleItems = leaderboard.items.slice(0, limit);
  if (visibleItems.length === 0) {
    return (
      <section>
        <h1>{leaderboard.category} leaderboard</h1>
        <p>No ranked services yet for this category.</p>
        <p>Try another category with ?category=&lt;name&gt;.</p>
      </section>
    );
  }

  return (
    <section>
      <h1>{leaderboard.category} leaderboard</h1>
      <p>
        Showing top {visibleItems.length} result{visibleItems.length === 1 ? "" : "s"}.
      </p>
      <div style={{ display: "grid", gap: 12, marginTop: 16 }}>
        {visibleItems.map((item, index) => (
          <article
            key={item.serviceSlug}
            style={{ border: "1px solid #e2e8f0", borderRadius: 12, padding: 16 }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
              <h2 style={{ margin: 0, fontSize: 18 }}>
                #{index + 1} <Link href={`/service/${item.serviceSlug}`}>{item.name}</Link>
              </h2>
              <strong>{scoreLabel(item.aggregateRecommendationScore)}</strong>
            </div>
            <div style={{ display: "flex", gap: 8, marginTop: 8, flexWrap: "wrap" }}>
              <span style={{ padding: "2px 8px", border: "1px solid #cbd5e1", borderRadius: 999 }}>
                Execution {scoreLabel(item.executionScore)}
              </span>
              <span style={{ padding: "2px 8px", border: "1px solid #cbd5e1", borderRadius: 999 }}>
                Access {scoreLabel(item.accessReadinessScore)}
              </span>
              <span style={{ padding: "2px 8px", border: "1px solid #cbd5e1", borderRadius: 999 }}>
                {item.tier ?? "Tier pending"}
              </span>
            </div>
            <p style={{ marginBottom: 0, marginTop: 8, color: "#475569" }}>
              Freshness: {freshnessLabel(item)}
            </p>
          </article>
        ))}
      </div>
    </section>
  );
}

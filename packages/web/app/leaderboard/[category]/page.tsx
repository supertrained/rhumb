import React from "react";
import Link from "next/link";
import type { Metadata } from "next";

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

function buildLeaderboardJsonLd(category: string, items: LeaderboardItem[]): Record<string, unknown> {
  return {
    "@context": "https://schema.org",
    "@type": "ItemList",
    name: `${category} leaderboard`,
    itemListOrder: "https://schema.org/ItemListOrderAscending",
    numberOfItems: items.length,
    itemListElement: items.map((item, index) => {
      const additionalProperty = [
        item.aggregateRecommendationScore !== null
          ? {
              "@type": "PropertyValue",
              name: "aggregate_recommendation_score",
              value: item.aggregateRecommendationScore.toFixed(1)
            }
          : null,
        item.executionScore !== null
          ? {
              "@type": "PropertyValue",
              name: "execution_score",
              value: item.executionScore.toFixed(1)
            }
          : null,
        item.accessReadinessScore !== null
          ? {
              "@type": "PropertyValue",
              name: "access_readiness_score",
              value: item.accessReadinessScore.toFixed(1)
            }
          : null
      ].filter(
        (property): property is { "@type": "PropertyValue"; name: string; value: string } =>
          property !== null
      );

      return {
        "@type": "ListItem",
        position: index + 1,
        item: {
          "@type": "SoftwareApplication",
          name: item.name,
          url: `/service/${item.serviceSlug}`,
          identifier: item.serviceSlug,
          ...(additionalProperty.length > 0 ? { additionalProperty } : {})
        }
      };
    })
  };
}

function renderJsonLd(payload: Record<string, unknown>): JSX.Element {
  return <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(payload) }} />;
}

export async function generateMetadata({
  params
}: {
  params: Promise<{ category: string }>;
}): Promise<Metadata> {
  const { category } = await params;

  return {
    title: `${category} leaderboard | Rhumb`,
    description: `Top agent-native services in ${category} ranked by aggregate, execution, and access-readiness scores.`
  };
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

  const resolvedCategory = leaderboard.error ? category : leaderboard.category;
  const visibleItems = leaderboard.error ? [] : leaderboard.items.slice(0, limit);
  const structuredData = buildLeaderboardJsonLd(resolvedCategory, visibleItems);

  if (leaderboard.error) {
    return (
      <section>
        {renderJsonLd(structuredData)}
        <h1>{category} leaderboard</h1>
        <p>We could not load leaderboard data right now.</p>
        <p>{leaderboard.error}</p>
      </section>
    );
  }

  if (visibleItems.length === 0) {
    return (
      <section>
        {renderJsonLd(structuredData)}
        <h1>{leaderboard.category} leaderboard</h1>
        <p>No ranked services yet for this category.</p>
        <p>Try another category with ?category=&lt;name&gt;.</p>
      </section>
    );
  }

  return (
    <section>
      {renderJsonLd(structuredData)}
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

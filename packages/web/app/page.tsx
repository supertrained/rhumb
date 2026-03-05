import React from "react";
import Link from "next/link";
import type { Metadata } from "next";

import { getLeaderboard } from "../lib/api";
import type { LeaderboardItem } from "../lib/types";

export const metadata: Metadata = {
  title: "Rhumb | Agent-native tool discovery",
  description: "Discover top agent-native services with execution and access-readiness evidence."
};

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

export default async function HomePage(): Promise<JSX.Element> {
  const leaderboard = await getLeaderboard("payments", { limit: 3 });
  const previewItems = leaderboard.items.slice(0, 3);

  return (
    <section>
      <header>
        <h1>Find agent-native services in seconds</h1>
        <p style={{ marginTop: 8 }}>
          Rhumb maps execution reliability and access readiness so your agents pick the right primitive
          before they fail in production.
        </p>

        <form
          action="/search"
          method="get"
          style={{ display: "flex", gap: 8, marginTop: 16, flexWrap: "wrap" }}
        >
          <input
            aria-label="Search services"
            name="q"
            placeholder="Search services (e.g. payments API)"
            style={{ minWidth: 260, padding: "8px 10px", borderRadius: 8, border: "1px solid #cbd5e1" }}
          />
          <button type="submit" style={{ padding: "8px 12px", borderRadius: 8 }}>
            Search
          </button>
        </form>

        <p style={{ marginTop: 12 }}>
          <Link href="/leaderboard/payments">Open full payments leaderboard</Link>
        </p>
      </header>

      <section style={{ marginTop: 28 }}>
        <h2>Top services in payments</h2>
        {leaderboard.error ? (
          <p>
            Live leaderboard preview is temporarily unavailable. You can still browse the
            <span> </span>
            <Link href="/leaderboard/payments">full leaderboard</Link>.
          </p>
        ) : previewItems.length === 0 ? (
          <p>No ranked services published yet.</p>
        ) : (
          <ol style={{ display: "grid", gap: 10, marginTop: 12, paddingLeft: 18 }}>
            {previewItems.map((item) => (
              <li key={item.serviceSlug}>
                <Link href={`/service/${item.serviceSlug}`}>{item.name}</Link>
                <span>{` · Aggregate ${scoreLabel(item.aggregateRecommendationScore)}`}</span>
                <span>{` · Freshness ${freshnessLabel(item)}`}</span>
              </li>
            ))}
          </ol>
        )}
      </section>
    </section>
  );
}

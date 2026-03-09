import React from "react";
import { ImageResponse } from "next/og";
import type { NextRequest } from "next/server";

import { getLeaderboard } from "../../../../lib/api";
import type { LeaderboardItem } from "../../../../lib/types";

export const runtime = "nodejs";

const WIDTH = 1200;
const HEIGHT = 630;

function capitalize(str: string): string {
  return str.charAt(0).toUpperCase() + str.slice(1);
}

function scoreText(value: number | null): string {
  return value === null ? "—" : value.toFixed(1);
}

function OGImage({
  category,
  items,
}: {
  category: string;
  items: LeaderboardItem[];
}): JSX.Element {
  return (
    <div
      style={{
        width: WIDTH,
        height: HEIGHT,
        display: "flex",
        flexDirection: "column",
        background: "#0f172a",
        color: "#f8fafc",
        fontFamily: "system-ui, sans-serif",
        padding: "60px 80px",
      }}
    >
      {/* Tagline */}
      <div
        style={{
          display: "flex",
          fontSize: 18,
          color: "#64748b",
          letterSpacing: "0.08em",
          textTransform: "uppercase",
          marginBottom: 16,
        }}
      >
        Agent-native tool ranking
      </div>

      {/* Category title */}
      <div
        style={{
          display: "flex",
          fontSize: 72,
          fontWeight: 800,
          color: "#f8fafc",
          lineHeight: 1.1,
          marginBottom: 40,
        }}
      >
        {capitalize(category)} Leaderboard
      </div>

      {/* Top services */}
      {items.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {items.slice(0, 3).map((item, i) => (
            <div
              key={item.serviceSlug}
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                background: "#1e293b",
                borderRadius: 10,
                padding: "14px 24px",
              }}
            >
              <div style={{ display: "flex", fontSize: 22, color: "#f1f5f9" }}>
                #{i + 1} {item.name}
              </div>
              <div
                style={{
                  display: "flex",
                  fontSize: 22,
                  fontWeight: 700,
                  color: "#22c55e",
                }}
              >
                {scoreText(item.aggregateRecommendationScore)}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Branding footer */}
      <div
        style={{
          display: "flex",
          marginTop: "auto",
          fontSize: 18,
          color: "#334155",
        }}
      >
        rhumb.dev
      </div>
    </div>
  );
}

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ category: string }> }
): Promise<Response> {
  const { category } = await params;

  let items: LeaderboardItem[] = [];
  try {
    const leaderboard = await getLeaderboard(category, { limit: 3 });
    if (!leaderboard.error) {
      items = leaderboard.items.slice(0, 3);
    }
  } catch {
    // Render fallback with category title only
  }

  return new ImageResponse(<OGImage category={category} items={items} />, {
    width: WIDTH,
    height: HEIGHT,
    headers: {
      "Cache-Control": "public, max-age=86400, s-maxage=86400",
    },
  });
}

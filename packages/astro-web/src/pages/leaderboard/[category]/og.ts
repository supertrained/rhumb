import type { APIRoute } from 'astro';
import { ImageResponse } from '@vercel/og';
import { getLeaderboard } from '../../../lib/api';
import type { LeaderboardItem } from '../../../lib/types';

const WIDTH = 1200;
const HEIGHT = 630;

function capitalize(str: string): string {
  return str.charAt(0).toUpperCase() + str.slice(1);
}

function scoreText(value: number | null): string {
  return value === null ? "—" : value.toFixed(1);
}

function buildOGImage(category: string, items: LeaderboardItem[]) {
  const topItems = items.slice(0, 3);

  return {
    type: "div",
    props: {
      style: {
        width: WIDTH,
        height: HEIGHT,
        display: "flex",
        flexDirection: "column",
        background: "#0f172a",
        color: "#f8fafc",
        fontFamily: "system-ui, sans-serif",
        padding: "60px 80px",
      },
      children: [
        // Tagline
        {
          type: "div",
          props: {
            style: {
              display: "flex",
              fontSize: 18,
              color: "#64748b",
              letterSpacing: "0.08em",
              textTransform: "uppercase",
              marginBottom: 16,
            },
            children: "Agent-native tool ranking",
          },
        },
        // Category title
        {
          type: "div",
          props: {
            style: {
              display: "flex",
              fontSize: 72,
              fontWeight: 800,
              color: "#f8fafc",
              lineHeight: 1.1,
              marginBottom: 40,
            },
            children: `${capitalize(category)} Leaderboard`,
          },
        },
        // Top services
        ...(topItems.length > 0
          ? [
              {
                type: "div",
                props: {
                  style: { display: "flex", flexDirection: "column", gap: 12 },
                  children: topItems.map((item, i) => ({
                    type: "div",
                    props: {
                      style: {
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "center",
                        background: "#1e293b",
                        borderRadius: 10,
                        padding: "14px 24px",
                      },
                      children: [
                        {
                          type: "div",
                          props: {
                            style: { display: "flex", fontSize: 22, color: "#f1f5f9" },
                            children: `#${i + 1} ${item.name}`,
                          },
                        },
                        {
                          type: "div",
                          props: {
                            style: {
                              display: "flex",
                              fontSize: 22,
                              fontWeight: 700,
                              color: "#22c55e",
                            },
                            children: scoreText(item.aggregateRecommendationScore),
                          },
                        },
                      ],
                    },
                  })),
                },
              },
            ]
          : []),
        // Branding footer
        {
          type: "div",
          props: {
            style: {
              display: "flex",
              marginTop: "auto",
              fontSize: 18,
              color: "#334155",
            },
            children: "rhumb.dev",
          },
        },
      ],
    },
  };
}

export const GET: APIRoute = async ({ params }) => {
  const { category } = params;

  if (!category) {
    return new Response(JSON.stringify({ error: "Category not found" }), {
      status: 404,
      headers: { "Content-Type": "application/json" },
    });
  }

  let items: LeaderboardItem[] = [];
  try {
    const leaderboard = await getLeaderboard(category, { limit: 3 });
    if (!leaderboard.error) {
      items = leaderboard.items.slice(0, 3);
    }
  } catch {
    // Render fallback with category title only
  }

  return new ImageResponse(buildOGImage(category, items) as any, {
    width: WIDTH,
    height: HEIGHT,
    headers: {
      "Cache-Control": "public, max-age=86400, s-maxage=86400",
    },
  });
};

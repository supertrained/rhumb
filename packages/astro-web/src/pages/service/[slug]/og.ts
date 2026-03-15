import type { APIRoute } from 'astro';
import { ImageResponse } from '@vercel/og';
import { getServiceScore } from '../../../lib/api';
import type { ServiceScoreViewModel } from '../../../lib/types';

const WIDTH = 1200;
const HEIGHT = 630;

type TierColors = {
  bg: string;
  text: string;
  label: string;
};

function tierColors(tier: string | null): TierColors {
  switch (tier) {
    case "L4":
      return { bg: "#7c3aed", text: "#ffffff", label: "Agent Native" };
    case "L3":
      return { bg: "#16a34a", text: "#ffffff", label: "Ready" };
    case "L2":
      return { bg: "#2563eb", text: "#ffffff", label: "Developing" };
    case "L1":
    default:
      return { bg: "#475569", text: "#ffffff", label: "Emerging" };
  }
}

function scoreText(value: number | null): string {
  return value === null ? "—" : value.toFixed(1);
}

function buildServiceOGImage(score: ServiceScoreViewModel) {
  const colors = tierColors(score.tier);
  const tierLabel = score.tierLabel ?? colors.label;

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
              marginBottom: 20,
            },
            children: "AN Score · rhumb.dev",
          },
        },
        // Service name
        {
          type: "div",
          props: {
            style: {
              display: "flex",
              fontSize: 80,
              fontWeight: 800,
              color: "#f8fafc",
              lineHeight: 1.0,
              marginBottom: 32,
            },
            children: score.serviceSlug,
          },
        },
        // Scores row
        {
          type: "div",
          props: {
            style: { display: "flex", gap: 20, marginBottom: 32 },
            children: [
              // Aggregate
              {
                type: "div",
                props: {
                  style: {
                    display: "flex",
                    flexDirection: "column",
                    background: "#1e293b",
                    borderRadius: 12,
                    padding: "20px 32px",
                    minWidth: 160,
                  },
                  children: [
                    {
                      type: "div",
                      props: {
                        style: { display: "flex", fontSize: 14, color: "#94a3b8", marginBottom: 8 },
                        children: "Aggregate",
                      },
                    },
                    {
                      type: "div",
                      props: {
                        style: { display: "flex", fontSize: 52, fontWeight: 800, color: "#22c55e" },
                        children: scoreText(score.aggregateRecommendationScore),
                      },
                    },
                  ],
                },
              },
              // Execution
              {
                type: "div",
                props: {
                  style: {
                    display: "flex",
                    flexDirection: "column",
                    background: "#1e293b",
                    borderRadius: 12,
                    padding: "20px 32px",
                    minWidth: 140,
                  },
                  children: [
                    {
                      type: "div",
                      props: {
                        style: { display: "flex", fontSize: 14, color: "#94a3b8", marginBottom: 8 },
                        children: "Execution",
                      },
                    },
                    {
                      type: "div",
                      props: {
                        style: { display: "flex", fontSize: 52, fontWeight: 700, color: "#f8fafc" },
                        children: scoreText(score.executionScore),
                      },
                    },
                  ],
                },
              },
              // Access
              {
                type: "div",
                props: {
                  style: {
                    display: "flex",
                    flexDirection: "column",
                    background: "#1e293b",
                    borderRadius: 12,
                    padding: "20px 32px",
                    minWidth: 140,
                  },
                  children: [
                    {
                      type: "div",
                      props: {
                        style: { display: "flex", fontSize: 14, color: "#94a3b8", marginBottom: 8 },
                        children: "Access",
                      },
                    },
                    {
                      type: "div",
                      props: {
                        style: { display: "flex", fontSize: 52, fontWeight: 700, color: "#f8fafc" },
                        children: scoreText(score.accessReadinessScore),
                      },
                    },
                  ],
                },
              },
              // Tier badge
              {
                type: "div",
                props: {
                  style: {
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    background: colors.bg,
                    color: colors.text,
                    borderRadius: 12,
                    padding: "20px 28px",
                    fontSize: 24,
                    fontWeight: 700,
                    marginLeft: "auto",
                  },
                  children: `${score.tier ?? "—"} · ${tierLabel}`,
                },
              },
            ],
          },
        },
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
            children: "Agent-native tool ranking · rhumb.dev",
          },
        },
      ],
    },
  };
}

export const GET: APIRoute = async ({ params }) => {
  const { slug } = params;

  if (!slug) {
    return new Response(JSON.stringify({ error: "Service not found" }), {
      status: 404,
      headers: { "Content-Type": "application/json" },
    });
  }

  const score = await getServiceScore(slug);

  if (score === null) {
    return new Response(JSON.stringify({ error: "Service not found" }), {
      status: 404,
      headers: { "Content-Type": "application/json" },
    });
  }

  return new ImageResponse(buildServiceOGImage(score) as any, {
    width: WIDTH,
    height: HEIGHT,
    headers: {
      "Cache-Control": "public, max-age=86400, s-maxage=86400",
    },
  });
};

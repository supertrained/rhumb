import React from "react";
import { ImageResponse } from "next/og";
import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

import { getServiceScore } from "../../../../lib/api";
import type { ServiceScoreViewModel } from "../../../../lib/types";

export const runtime = "nodejs";

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

function ServiceOGImage({ score }: { score: ServiceScoreViewModel }): JSX.Element {
  const colors = tierColors(score.tier);
  const tierLabel = score.tierLabel ?? colors.label;

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
          marginBottom: 20,
        }}
      >
        AN Score · rhumb.dev
      </div>

      {/* Service name */}
      <div
        style={{
          display: "flex",
          fontSize: 80,
          fontWeight: 800,
          color: "#f8fafc",
          lineHeight: 1.0,
          marginBottom: 32,
        }}
      >
        {score.serviceSlug}
      </div>

      {/* Scores row */}
      <div style={{ display: "flex", gap: 20, marginBottom: 32 }}>
        {/* Aggregate */}
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            background: "#1e293b",
            borderRadius: 12,
            padding: "20px 32px",
            minWidth: 160,
          }}
        >
          <div style={{ display: "flex", fontSize: 14, color: "#94a3b8", marginBottom: 8 }}>
            Aggregate
          </div>
          <div style={{ display: "flex", fontSize: 52, fontWeight: 800, color: "#22c55e" }}>
            {scoreText(score.aggregateRecommendationScore)}
          </div>
        </div>

        {/* Execution */}
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            background: "#1e293b",
            borderRadius: 12,
            padding: "20px 32px",
            minWidth: 140,
          }}
        >
          <div style={{ display: "flex", fontSize: 14, color: "#94a3b8", marginBottom: 8 }}>
            Execution
          </div>
          <div style={{ display: "flex", fontSize: 52, fontWeight: 700, color: "#f8fafc" }}>
            {scoreText(score.executionScore)}
          </div>
        </div>

        {/* Access */}
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            background: "#1e293b",
            borderRadius: 12,
            padding: "20px 32px",
            minWidth: 140,
          }}
        >
          <div style={{ display: "flex", fontSize: 14, color: "#94a3b8", marginBottom: 8 }}>
            Access
          </div>
          <div style={{ display: "flex", fontSize: 52, fontWeight: 700, color: "#f8fafc" }}>
            {scoreText(score.accessReadinessScore)}
          </div>
        </div>

        {/* Tier badge */}
        <div
          style={{
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
          }}
        >
          {score.tier ?? "—"} · {tierLabel}
        </div>
      </div>

      {/* Branding footer */}
      <div
        style={{
          display: "flex",
          marginTop: "auto",
          fontSize: 18,
          color: "#334155",
        }}
      >
        Agent-native tool ranking · rhumb.dev
      </div>
    </div>
  );
}

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ slug: string }> }
): Promise<Response> {
  const { slug } = await params;

  const score = await getServiceScore(slug);

  if (score === null) {
    return NextResponse.json({ error: "Service not found" }, { status: 404 });
  }

  return new ImageResponse(<ServiceOGImage score={score} />, {
    width: WIDTH,
    height: HEIGHT,
    headers: {
      "Cache-Control": "public, max-age=86400, s-maxage=86400",
    },
  });
}

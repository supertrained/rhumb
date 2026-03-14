import { ImageResponse } from "next/og";
import type { NextRequest } from "next/server";

export const runtime = "edge";

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const title = searchParams.get("title") || "Agent-Native Tool Discovery";
  const subtitle =
    searchParams.get("subtitle") ||
    "Every API scored for AI agent compatibility";

  return new ImageResponse(
    (
      <div
        style={{
          height: "100%",
          width: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          backgroundColor: "#0B1120",
          padding: "60px 80px",
          fontFamily: "system-ui, sans-serif",
        }}
      >
        {/* Top accent line */}
        <div
          style={{
            position: "absolute",
            top: 0,
            left: 0,
            right: 0,
            height: "4px",
            background: "linear-gradient(90deg, #F59E0B, #D97706, #F59E0B)",
          }}
        />

        {/* Logo */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            marginBottom: "40px",
          }}
        >
          <span
            style={{
              fontSize: "32px",
              fontWeight: 700,
              color: "#F1F5F9",
              letterSpacing: "-0.02em",
            }}
          >
            rhumb
          </span>
          <span style={{ fontSize: "32px", fontWeight: 700, color: "#F59E0B" }}>
            .
          </span>
        </div>

        {/* Title */}
        <div
          style={{
            fontSize: "56px",
            fontWeight: 700,
            color: "#F1F5F9",
            lineHeight: 1.15,
            letterSpacing: "-0.03em",
            marginBottom: "20px",
            maxWidth: "900px",
          }}
        >
          {title}
        </div>

        {/* Subtitle */}
        <div
          style={{
            fontSize: "24px",
            color: "#94A3B8",
            lineHeight: 1.4,
            maxWidth: "700px",
          }}
        >
          {subtitle}
        </div>

        {/* Bottom bar */}
        <div
          style={{
            position: "absolute",
            bottom: "40px",
            left: "80px",
            right: "80px",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
          }}
        >
          <span style={{ fontSize: "16px", color: "#64748B" }}>
            rhumb.dev
          </span>
          <div style={{ display: "flex", gap: "24px" }}>
            <span style={{ fontSize: "14px", color: "#475569" }}>
              20 dimensions
            </span>
            <span style={{ fontSize: "14px", color: "#475569" }}>·</span>
            <span style={{ fontSize: "14px", color: "#475569" }}>
              2 axes
            </span>
            <span style={{ fontSize: "14px", color: "#475569" }}>·</span>
            <span style={{ fontSize: "14px", color: "#475569" }}>
              Fully transparent
            </span>
          </div>
        </div>
      </div>
    ),
    {
      width: 1200,
      height: 630,
    },
  );
}

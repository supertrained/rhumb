import { ImageResponse } from "next/og";

export const runtime = "nodejs";

export async function GET() {
  return new ImageResponse(
    (
      <div
        style={{
          width: 1200,
          height: 630,
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          padding: "60px 80px",
          background: "linear-gradient(135deg, #0f172a 0%, #1e293b 100%)",
          color: "white",
          fontFamily: "system-ui, -apple-system, sans-serif",
        }}
      >
        <div
          style={{
            display: "flex",
            fontSize: 16,
            color: "#a78bfa",
            fontWeight: 600,
            letterSpacing: 2,
            marginBottom: 24,
          }}
        >
          TOOL AUTOPSY
        </div>
        <div
          style={{
            display: "flex",
            fontSize: 48,
            fontWeight: 800,
            lineHeight: 1.2,
            marginBottom: 32,
          }}
        >
          Why Stripe Scores 8.3 and PayPal Scores 5.2 for AI Agents
        </div>

        {/* Mini leaderboard */}
        <div
          style={{
            display: "flex",
            gap: 32,
            marginBottom: 40,
          }}
        >
          {[
            { name: "Stripe", score: "8.3", color: "#7c3aed" },
            { name: "Lemon Squeezy", score: "7.0", color: "#059669" },
            { name: "PayPal", score: "5.2", color: "#dc2626" },
          ].map((t) => (
            <div
              key={t.name}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
              }}
            >
              <div
                style={{
                  display: "flex",
                  width: 8,
                  height: 8,
                  borderRadius: 999,
                  background: t.color,
                }}
              />
              <span style={{ fontSize: 20, fontWeight: 600, display: "flex" }}>
                {t.name}
              </span>
              <span style={{ fontSize: 20, color: "#94a3b8", display: "flex" }}>{t.score}</span>
            </div>
          ))}
        </div>

        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
          }}
        >
          <div style={{ display: "flex", fontSize: 18, color: "#64748b" }}>
            rhumb.dev · Agent-Native Score
          </div>
        </div>
      </div>
    ),
    {
      width: 1200,
      height: 630,
    }
  );
}

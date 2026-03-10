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
            color: "#f59e0b",
            fontWeight: 600,
            letterSpacing: 2,
            marginBottom: 24,
          }}
        >
          FRAMEWORK
        </div>
        <div
          style={{
            display: "flex",
            fontSize: 44,
            fontWeight: 800,
            lineHeight: 1.2,
            marginBottom: 32,
          }}
        >
          The WCAG for AI Agents
        </div>

        <div
          style={{
            display: "flex",
            fontSize: 22,
            color: "#94a3b8",
            lineHeight: 1.5,
            marginBottom: 40,
          }}
        >
          Agent Accessibility Guidelines: 6 interaction channels × 3 compliance
          levels. The framework for building web apps that work for autonomous AI
          agents.
        </div>

        {/* Level badges */}
        <div
          style={{
            display: "flex",
            gap: 24,
            marginBottom: 40,
          }}
        >
          {[
            { level: "Level A", label: "Parseable", color: "#f59e0b" },
            { level: "Level AA", label: "Navigable", color: "#3b82f6" },
            { level: "Level AAA", label: "Native", color: "#10b981" },
          ].map((t) => (
            <div
              key={t.level}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 10,
                padding: "8px 16px",
                borderRadius: 8,
                border: `2px solid ${t.color}40`,
                background: `${t.color}10`,
              }}
            >
              <span
                style={{
                  fontSize: 18,
                  fontWeight: 700,
                  color: t.color,
                  display: "flex",
                }}
              >
                {t.level}
              </span>
              <span
                style={{ fontSize: 16, color: "#94a3b8", display: "flex" }}
              >
                {t.label}
              </span>
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
            rhumb.dev · Agent Accessibility Guidelines
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

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import { describe, expect, it } from "vitest";

import { AutonomyBadges } from "../components/autonomy-badges";
import { AutonomySection } from "../components/autonomy-section";

// ── AutonomyBadges ─────────────────────────────────────────────────

describe("AutonomyBadges", () => {
  it("renders P1 ✓ when p1Score >= 5.0", () => {
    const html = renderToStaticMarkup(
      React.createElement(AutonomyBadges, { p1Score: 8.1, g1Score: null, w1Score: null })
    );
    expect(html).toContain("P1: ✓");
  });

  it("renders P1 ✗ when p1Score < 5.0", () => {
    const html = renderToStaticMarkup(
      React.createElement(AutonomyBadges, { p1Score: 3.2, g1Score: null, w1Score: null })
    );
    expect(html).toContain("P1: ✗");
  });

  it("renders P1 — when p1Score is null", () => {
    const html = renderToStaticMarkup(
      React.createElement(AutonomyBadges, { p1Score: null, g1Score: null, w1Score: null })
    );
    expect(html).toContain("P1: —");
  });

  it("renders G1 ✓ when g1Score >= 5.0", () => {
    const html = renderToStaticMarkup(
      React.createElement(AutonomyBadges, { p1Score: null, g1Score: 7.5, w1Score: null })
    );
    expect(html).toContain("G1: ✓");
  });

  it("renders G1 ✗ when g1Score < 5.0", () => {
    const html = renderToStaticMarkup(
      React.createElement(AutonomyBadges, { p1Score: null, g1Score: 4.9, w1Score: null })
    );
    expect(html).toContain("G1: ✗");
  });

  it("renders W1 ◐ for score 0–6", () => {
    const html = renderToStaticMarkup(
      React.createElement(AutonomyBadges, { p1Score: null, g1Score: null, w1Score: 5.0 })
    );
    expect(html).toContain("W1: ◐");
  });

  it("renders W1 ◑ for score 6–8", () => {
    const html = renderToStaticMarkup(
      React.createElement(AutonomyBadges, { p1Score: null, g1Score: null, w1Score: 7.0 })
    );
    expect(html).toContain("W1: ◑");
  });

  it("renders W1 ◕ for score 8+", () => {
    const html = renderToStaticMarkup(
      React.createElement(AutonomyBadges, { p1Score: null, g1Score: null, w1Score: 8.5 })
    );
    expect(html).toContain("W1: ◕");
  });

  it("renders all three badges together", () => {
    const html = renderToStaticMarkup(
      React.createElement(AutonomyBadges, { p1Score: 8.1, g1Score: 9.2, w1Score: 7.9 })
    );
    expect(html).toContain("P1: ✓");
    expect(html).toContain("G1: ✓");
    expect(html).toContain("W1: ◑");
  });

  it("renders all nulls as — without errors", () => {
    const html = renderToStaticMarkup(
      React.createElement(AutonomyBadges, { p1Score: null, g1Score: null, w1Score: null })
    );
    expect(html).toContain("P1: —");
    expect(html).toContain("G1: —");
    expect(html).toContain("W1: —");
  });

  it("includes tooltip title attributes", () => {
    const html = renderToStaticMarkup(
      React.createElement(AutonomyBadges, { p1Score: 7.2, g1Score: 8.0, w1Score: 6.5 })
    );
    expect(html).toContain("P1: Payment Autonomy");
    expect(html).toContain("G1: Governance Readiness");
    expect(html).toContain("W1: Web Agent Accessibility");
  });

  it("applies emerald color class for passing P1 score", () => {
    const html = renderToStaticMarkup(
      React.createElement(AutonomyBadges, { p1Score: 6.0, g1Score: null, w1Score: null })
    );
    expect(html).toContain("text-score-native");
  });

  it("applies red color class for failing P1 score", () => {
    const html = renderToStaticMarkup(
      React.createElement(AutonomyBadges, { p1Score: 2.5, g1Score: null, w1Score: null })
    );
    expect(html).toContain("text-score-limited");
  });

  it("applies amber color class for partial W1 score", () => {
    const html = renderToStaticMarkup(
      React.createElement(AutonomyBadges, { p1Score: null, g1Score: null, w1Score: 4.0 })
    );
    expect(html).toContain("text-amber");
  });

  it("applies blue color class for good W1 score", () => {
    const html = renderToStaticMarkup(
      React.createElement(AutonomyBadges, { p1Score: null, g1Score: null, w1Score: 6.5 })
    );
    expect(html).toContain("text-score-ready");
  });

  it("applies emerald color class for strong W1 score", () => {
    const html = renderToStaticMarkup(
      React.createElement(AutonomyBadges, { p1Score: null, g1Score: null, w1Score: 9.0 })
    );
    // W1 >= 8 gets text-score-native (emerald)
    expect(html).toContain("text-score-native");
  });

  it("has data-testid for targeting", () => {
    const html = renderToStaticMarkup(
      React.createElement(AutonomyBadges, { p1Score: null, g1Score: null, w1Score: null })
    );
    expect(html).toContain("data-testid=\"autonomy-badges\"");
  });

  it("handles boundary value W1=6.0 as ◑ (good)", () => {
    const html = renderToStaticMarkup(
      React.createElement(AutonomyBadges, { p1Score: null, g1Score: null, w1Score: 6.0 })
    );
    expect(html).toContain("W1: ◑");
  });

  it("handles boundary value W1=8.0 as ◕ (strong)", () => {
    const html = renderToStaticMarkup(
      React.createElement(AutonomyBadges, { p1Score: null, g1Score: null, w1Score: 8.0 })
    );
    expect(html).toContain("W1: ◕");
  });

  it("handles boundary value P1=5.0 as ✓", () => {
    const html = renderToStaticMarkup(
      React.createElement(AutonomyBadges, { p1Score: 5.0, g1Score: null, w1Score: null })
    );
    expect(html).toContain("P1: ✓");
  });
});

// ── AutonomySection ────────────────────────────────────────────────

describe("AutonomySection", () => {
  const baseProps = {
    p1Score: 5.2,
    g1Score: 8.0,
    w1Score: 7.2,
    p1Rationale: "Accepts Stripe ACP + Coinbase AgentKit. No x402 or AP2 yet.",
    g1Rationale: "Full RBAC, audit logs, SOC 2 Type II.",
    w1Rationale: "Dashboard has AAG Level 2. Missing ChatGPT Skills integration.",
    autonomyTier: "L3",
  };

  it("renders section heading", () => {
    const html = renderToStaticMarkup(React.createElement(AutonomySection, baseProps));
    expect(html).toContain("Autonomy breakdown");
  });

  it("renders P1, G1, W1 codes", () => {
    const html = renderToStaticMarkup(React.createElement(AutonomySection, baseProps));
    expect(html).toContain("P1");
    expect(html).toContain("G1");
    expect(html).toContain("W1");
  });

  it("renders dimension labels", () => {
    const html = renderToStaticMarkup(React.createElement(AutonomySection, baseProps));
    expect(html).toContain("Payment Autonomy");
    expect(html).toContain("Governance Readiness");
    expect(html).toContain("Web Agent Accessibility");
  });

  it("renders dimension scores", () => {
    const html = renderToStaticMarkup(React.createElement(AutonomySection, baseProps));
    expect(html).toContain("5.2");
    expect(html).toContain("8.0");
    expect(html).toContain("7.2");
  });

  it("renders rationale text", () => {
    const html = renderToStaticMarkup(React.createElement(AutonomySection, baseProps));
    expect(html).toContain("Accepts Stripe ACP + Coinbase AgentKit");
    expect(html).toContain("Full RBAC, audit logs");
    expect(html).toContain("AAG Level 2");
  });

  it("shows 'Ready for agent use' when average >= 6.0", () => {
    const html = renderToStaticMarkup(
      React.createElement(AutonomySection, {
        ...baseProps,
        p1Score: 7.0,
        g1Score: 7.0,
        w1Score: 7.0,
      })
    );
    expect(html).toContain("Ready for agent use");
  });

  it("shows 'Limited' when average < 6.0", () => {
    const html = renderToStaticMarkup(
      React.createElement(AutonomySection, {
        ...baseProps,
        p1Score: 3.0,
        g1Score: 4.0,
        w1Score: 4.0,
      })
    );
    expect(html).toContain("Limited");
  });

  it("renders 'Pending' when all scores are null", () => {
    const html = renderToStaticMarkup(
      React.createElement(AutonomySection, {
        p1Score: null,
        g1Score: null,
        w1Score: null,
        p1Rationale: null,
        g1Rationale: null,
        w1Rationale: null,
        autonomyTier: null,
      })
    );
    expect(html).toContain("Pending");
  });

  it("renders — for null scores", () => {
    const html = renderToStaticMarkup(
      React.createElement(AutonomySection, {
        p1Score: null,
        g1Score: null,
        w1Score: null,
        p1Rationale: null,
        g1Rationale: null,
        w1Rationale: null,
        autonomyTier: null,
      })
    );
    // Each dimension should show — for score
    expect(html.match(/—/g)?.length).toBeGreaterThanOrEqual(3);
  });

  it("skips rationale markup when rationale is null", () => {
    const html = renderToStaticMarkup(
      React.createElement(AutonomySection, {
        ...baseProps,
        p1Rationale: null,
      })
    );
    // No p1 rationale text should be present
    expect(html).not.toContain("Accepts Stripe ACP");
    // But other rationale should still be present
    expect(html).toContain("Full RBAC");
  });

  it("renders overall autonomy score in summary row", () => {
    const html = renderToStaticMarkup(
      React.createElement(AutonomySection, {
        ...baseProps,
        p1Score: 6.0,
        g1Score: 6.0,
        w1Score: 6.0,
      })
    );
    expect(html).toContain("Overall Autonomy");
    expect(html).toContain("6.0/10");
  });

  it("has data-testid for targeting", () => {
    const html = renderToStaticMarkup(React.createElement(AutonomySection, baseProps));
    expect(html).toContain("data-testid=\"autonomy-section\"");
  });
});

// ── Adapter integration: p1/g1/w1 round-trip ──────────────────────

describe("adapter autonomy field parsing", () => {
  it("parses p1/g1/w1 scores from leaderboard payload", async () => {
    const { parseLeaderboardResponse } = await import("../lib/adapters");

    const payload = {
      data: {
        category: "payments",
        items: [
          {
            service_slug: "stripe",
            name: "Stripe",
            aggregate_recommendation_score: 8.9,
            execution_score: 9.1,
            access_readiness_score: 8.4,
            probe_freshness: "5 min ago",
            calculated_at: "2026-03-10T00:00:00Z",
            tier: "L4",
            confidence: 0.95,
            p1_score: 8.1,
            g1_score: 9.2,
            w1_score: 7.9,
          },
        ],
      },
      error: null,
    };

    const result = parseLeaderboardResponse(payload);
    expect(result.items[0].p1Score).toBe(8.1);
    expect(result.items[0].g1Score).toBe(9.2);
    expect(result.items[0].w1Score).toBe(7.9);
  });

  it("parses autonomy fields from service score payload", async () => {
    const { parseServiceScoreResponse } = await import("../lib/adapters");

    const payload = {
      service_slug: "stripe",
      aggregate_recommendation_score: 8.9,
      execution_score: 9.1,
      access_readiness_score: 8.4,
      confidence: 0.98,
      tier: "L4",
      tier_label: "Agent Native",
      explanation: "Reliable",
      calculated_at: "2026-03-10T00:00:00Z",
      dimension_snapshot: { probe_freshness: "5 min ago" },
      p1_score: 8.1,
      g1_score: 9.2,
      w1_score: 7.9,
      p1_rationale: "Accepts Stripe ACP",
      g1_rationale: "Full RBAC",
      w1_rationale: "AAG Level 2",
      autonomy_tier: "L3",
    };

    const result = parseServiceScoreResponse(payload);
    expect(result).not.toBeNull();
    expect(result!.p1Score).toBe(8.1);
    expect(result!.g1Score).toBe(9.2);
    expect(result!.w1Score).toBe(7.9);
    expect(result!.p1Rationale).toBe("Accepts Stripe ACP");
    expect(result!.g1Rationale).toBe("Full RBAC");
    expect(result!.w1Rationale).toBe("AAG Level 2");
    expect(result!.autonomyTier).toBe("L3");
  });

  it("returns null for all autonomy fields when not present in payload", async () => {
    const { parseServiceScoreResponse } = await import("../lib/adapters");

    const payload = {
      service_slug: "stripe",
      aggregate_recommendation_score: 8.9,
      execution_score: 9.1,
      access_readiness_score: 8.4,
      confidence: 0.98,
      tier: "L4",
      tier_label: null,
      explanation: null,
      calculated_at: null,
      dimension_snapshot: {},
    };

    const result = parseServiceScoreResponse(payload);
    expect(result).not.toBeNull();
    expect(result!.p1Score).toBeNull();
    expect(result!.g1Score).toBeNull();
    expect(result!.w1Score).toBeNull();
    expect(result!.p1Rationale).toBeNull();
    expect(result!.g1Rationale).toBeNull();
    expect(result!.w1Rationale).toBeNull();
    expect(result!.autonomyTier).toBeNull();
  });
});

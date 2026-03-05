import { describe, expect, it, vi } from "vitest";

vi.mock("../lib/api", () => ({
  getLeaderboard: vi.fn(async () => ({ category: "payments", items: [], error: null })),
  getServiceScore: vi.fn(async () => ({
    serviceSlug: "stripe",
    aggregateRecommendationScore: 8.9,
    executionScore: 9.1,
    accessReadinessScore: 8.4,
    confidence: 0.98,
    tier: "L4",
    tierLabel: "Agent Native",
    explanation: "Reliable payment API",
    calculatedAt: "2026-03-05T23:00:00Z",
    evidenceFreshness: "12 minutes ago",
    activeFailures: [],
    alternatives: []
  }))
}));

describe("round 7 slice A route scaffold", () => {
  it("renders home route component", async () => {
    const module = await import("../app/page");
    const node = await module.default();

    expect(node).toBeTruthy();
  });

  it("renders leaderboard route component", async () => {
    const module = await import("../app/leaderboard/[category]/page");
    const node = await module.default({
      params: Promise.resolve({ category: "payments" }),
      searchParams: Promise.resolve({})
    });

    expect(node).toBeTruthy();
  });

  it("renders service route component", async () => {
    const module = await import("../app/service/[slug]/page");
    const node = await module.default({ params: Promise.resolve({ slug: "stripe" }) });

    expect(node).toBeTruthy();
  });
});

import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { getLeaderboardMock } = vi.hoisted(() => ({
  getLeaderboardMock: vi.fn()
}));

vi.mock("../lib/api", () => ({
  getLeaderboard: getLeaderboardMock
}));

async function renderHomePage(): Promise<string> {
  const module = await import("../app/page");
  const page = await module.default();
  return renderToStaticMarkup(page);
}

describe("home page", () => {
  beforeEach(() => {
    getLeaderboardMock.mockReset();
  });

  it("renders hero, search entry, and leaderboard preview", async () => {
    getLeaderboardMock.mockResolvedValue({
      category: "payments",
      error: null,
      items: [
        {
          serviceSlug: "stripe",
          name: "Stripe",
          aggregateRecommendationScore: 8.9,
          executionScore: 9.1,
          accessReadinessScore: 8.4,
          freshness: "12 minutes ago",
          calculatedAt: null,
          tier: "L4",
          confidence: 0.95
        }
      ]
    });

    const html = await renderHomePage();

    expect(getLeaderboardMock).toHaveBeenCalledWith("payments", { limit: 3 });
    expect(html).toContain("Find agent-native services in seconds");
    expect(html).toContain("placeholder=\"Search services (e.g. payments API)\"");
    expect(html).toContain("Open full payments leaderboard");
    expect(html).toContain("Stripe</a>");
    expect(html).toContain("Aggregate 8.9");
  });

  it("renders even when leaderboard preview fails", async () => {
    getLeaderboardMock.mockResolvedValue({
      category: "payments",
      error: "Unable to load leaderboard right now.",
      items: []
    });

    const html = await renderHomePage();

    expect(html).toContain("Find agent-native services in seconds");
    expect(html).toContain("Live leaderboard preview is temporarily unavailable.");
    expect(html).toContain("full leaderboard");
  });
});

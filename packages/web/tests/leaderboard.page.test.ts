import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { getLeaderboardMock } = vi.hoisted(() => ({
  getLeaderboardMock: vi.fn()
}));

vi.mock("../lib/api", () => ({
  getLeaderboard: getLeaderboardMock
}));

type PageInput = {
  params?: { category: string };
  searchParams?: { category?: string; limit?: string };
};

async function renderLeaderboardPage(input: PageInput = {}): Promise<string> {
  const module = await import("../app/leaderboard/[category]/page");
  const page = await module.default({
    params: Promise.resolve(input.params ?? { category: "payments" }),
    searchParams: Promise.resolve(input.searchParams ?? {})
  });

  return renderToStaticMarkup(page);
}

describe("leaderboard page", () => {
  beforeEach(() => {
    getLeaderboardMock.mockReset();
  });

  it("generates baseline metadata", async () => {
    const module = await import("../app/leaderboard/[category]/page");
    const metadata = await module.generateMetadata({ params: Promise.resolve({ category: "payments" }) });

    expect(metadata.title).toBe("payments leaderboard | Rhumb");
    expect(metadata.description).toContain("payments");
  });

  it("renders ranked entries with execution/access badges and freshness", async () => {
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
        },
        {
          serviceSlug: "resend",
          name: "Resend",
          aggregateRecommendationScore: 8.1,
          executionScore: 8.3,
          accessReadinessScore: 7.8,
          freshness: "2 hours ago",
          calculatedAt: null,
          tier: "L3",
          confidence: 0.9
        }
      ]
    });

    const html = await renderLeaderboardPage({ searchParams: { limit: "1" } });

    expect(getLeaderboardMock).toHaveBeenCalledWith("payments", { limit: 1 });
    expect(html).toContain("#1");
    expect(html).toContain("Execution 9.1");
    expect(html).toContain("Access 8.4");
    expect(html).toContain("Freshness: 12 minutes ago");
    expect(html).toContain("application/ld+json");
    expect(html).toContain('"@type":"ItemList"');
    expect(html).toContain('"name":"payments leaderboard"');
    expect(html).not.toContain("Resend");
  });

  it("renders empty state snapshot", async () => {
    getLeaderboardMock.mockResolvedValue({
      category: "payments",
      error: null,
      items: []
    });

    const html = await renderLeaderboardPage();

    expect(html).toMatchInlineSnapshot(
      '"<section><script type=\"application/ld+json\">{\"@context\":\"https://schema.org\",\"@type\":\"ItemList\",\"name\":\"payments leaderboard\",\"itemListOrder\":\"https://schema.org/ItemListOrderAscending\",\"numberOfItems\":0,\"itemListElement\":[]}</script><h1>payments leaderboard</h1><p>No ranked services yet for this category.</p><p>Try another category with ?category=&lt;name&gt;.</p></section>"'
    );
  });

  it("renders error state snapshot", async () => {
    getLeaderboardMock.mockResolvedValue({
      category: "payments",
      error: "Unable to load leaderboard right now.",
      items: []
    });

    const html = await renderLeaderboardPage();

    expect(html).toMatchInlineSnapshot(
      '"<section><script type=\"application/ld+json\">{\"@context\":\"https://schema.org\",\"@type\":\"ItemList\",\"name\":\"payments leaderboard\",\"itemListOrder\":\"https://schema.org/ItemListOrderAscending\",\"numberOfItems\":0,\"itemListElement\":[]}</script><h1>payments leaderboard</h1><p>We could not load leaderboard data right now.</p><p>Unable to load leaderboard right now.</p></section>"'
    );
  });
});

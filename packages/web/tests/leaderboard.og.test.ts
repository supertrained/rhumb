/**
 * WU 3.1 Slice B — Leaderboard OG image route tests
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

// Mock next/og before any imports that use it
vi.mock("next/og", () => ({
  ImageResponse: class MockImageResponse extends Response {
    constructor(_element: unknown, options?: { width?: number; height?: number; headers?: Record<string, string> }) {
      super("PNG-mock-data", {
        status: 200,
        headers: {
          "Content-Type": "image/png",
          ...(options?.headers ?? {}),
        },
      });
    }
  },
}));

const { getLeaderboardMock } = vi.hoisted(() => ({
  getLeaderboardMock: vi.fn(),
}));

vi.mock("../lib/api", () => ({
  getLeaderboard: getLeaderboardMock,
}));

const MOCK_LEADERBOARD = {
  category: "payments",
  error: null,
  items: [
    {
      serviceSlug: "stripe",
      name: "Stripe",
      aggregateRecommendationScore: 8.9,
      executionScore: 9.1,
      accessReadinessScore: 8.4,
      freshness: null,
      calculatedAt: null,
      tier: "L4",
      confidence: 0.95,
    },
    {
      serviceSlug: "paddle",
      name: "Paddle",
      aggregateRecommendationScore: 7.8,
      executionScore: 7.9,
      accessReadinessScore: 7.5,
      freshness: null,
      calculatedAt: null,
      tier: "L3",
      confidence: 0.9,
    },
    {
      serviceSlug: "square",
      name: "Square",
      aggregateRecommendationScore: 7.2,
      executionScore: 7.3,
      accessReadinessScore: 7.0,
      freshness: null,
      calculatedAt: null,
      tier: "L3",
      confidence: 0.88,
    },
  ],
};

function makeRequest(url = "http://localhost/leaderboard/payments/og"): Request {
  return new Request(url);
}

async function callOGRoute(category = "payments"): Promise<Response> {
  const mod = await import("../app/leaderboard/[category]/og/route");
  return mod.GET(makeRequest() as Parameters<typeof mod.GET>[0], {
    params: Promise.resolve({ category }),
  });
}

describe("leaderboard OG route", () => {
  beforeEach(() => {
    getLeaderboardMock.mockReset();
    getLeaderboardMock.mockResolvedValue(MOCK_LEADERBOARD);
  });

  it("responds with 200", async () => {
    const res = await callOGRoute("payments");
    expect(res.status).toBe(200);
  });

  it("responds with image/png content type", async () => {
    const res = await callOGRoute("payments");
    expect(res.headers.get("Content-Type")).toBe("image/png");
  });

  it("fetches leaderboard data with limit 3", async () => {
    await callOGRoute("payments");
    expect(getLeaderboardMock).toHaveBeenCalledWith("payments", { limit: 3 });
  });

  it("fetches correct category from params", async () => {
    getLeaderboardMock.mockResolvedValue({ ...MOCK_LEADERBOARD, category: "auth" });
    await callOGRoute("auth");
    expect(getLeaderboardMock).toHaveBeenCalledWith("auth", { limit: 3 });
  });

  it("renders even when leaderboard returns error", async () => {
    getLeaderboardMock.mockResolvedValue({
      category: "payments",
      error: "Category not found",
      items: [],
    });
    const res = await callOGRoute("payments");
    expect(res.status).toBe(200);
    expect(res.headers.get("Content-Type")).toBe("image/png");
  });

  it("renders even when getLeaderboard throws", async () => {
    getLeaderboardMock.mockRejectedValue(new Error("Network error"));
    const res = await callOGRoute("payments");
    expect(res.status).toBe(200);
    expect(res.headers.get("Content-Type")).toBe("image/png");
  });

  it("works for all 10 categories", async () => {
    const categories = ["payments", "ai", "analytics", "auth", "calendar", "crm", "devops", "email", "search", "social"];
    for (const cat of categories) {
      getLeaderboardMock.mockResolvedValue({ category: cat, error: null, items: [] });
      const res = await callOGRoute(cat);
      expect(res.status).toBe(200);
    }
  });

  // ── Metadata injection in category page ──

  it("category page generateMetadata includes OG image URL", async () => {
    const pageMod = await import("../app/leaderboard/[category]/page");
    const meta = await pageMod.generateMetadata({
      params: Promise.resolve({ category: "payments" }),
    });
    const ogImages = (meta.openGraph as { images?: unknown[] } | undefined)?.images;
    expect(Array.isArray(ogImages)).toBe(true);
    const firstImage = (ogImages as Array<{ url?: string }>)[0];
    expect(firstImage?.url).toBe("/leaderboard/payments/og");
  });

  it("category page generateMetadata OG image has correct dimensions", async () => {
    const pageMod = await import("../app/leaderboard/[category]/page");
    const meta = await pageMod.generateMetadata({
      params: Promise.resolve({ category: "search" }),
    });
    const ogImages = (meta.openGraph as { images?: Array<{ width?: number; height?: number }> } | undefined)?.images ?? [];
    expect(ogImages[0]?.width).toBe(1200);
    expect(ogImages[0]?.height).toBe(630);
  });

  it("category page generateMetadata includes canonical URL", async () => {
    const pageMod = await import("../app/leaderboard/[category]/page");
    const meta = await pageMod.generateMetadata({
      params: Promise.resolve({ category: "email" }),
    });
    expect((meta.alternates as { canonical?: string } | undefined)?.canonical).toBe("/leaderboard/email");
  });
});

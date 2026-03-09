/**
 * WU 3.1 Slice C — Service OG image route tests
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

// Mock next/og before any imports
vi.mock("next/og", () => ({
  ImageResponse: class MockImageResponse extends Response {
    constructor(_element: unknown, options?: { width?: number; height?: number; headers?: Record<string, string> }) {
      super("PNG-mock-service", {
        status: 200,
        headers: {
          "Content-Type": "image/png",
          ...(options?.headers ?? {}),
        },
      });
    }
  },
}));

const { getServiceScoreMock } = vi.hoisted(() => ({
  getServiceScoreMock: vi.fn(),
}));

vi.mock("../lib/api", () => ({
  getServiceScore: getServiceScoreMock,
}));

const BASE_SCORE = {
  serviceSlug: "stripe",
  aggregateRecommendationScore: 8.9,
  executionScore: 9.1,
  accessReadinessScore: 8.4,
  confidence: 0.98,
  tier: "L4",
  tierLabel: "Agent Native",
  explanation: "Reliable payment API",
  calculatedAt: "2026-03-09T00:00:00Z",
  evidenceFreshness: "5 minutes ago",
  activeFailures: [],
  alternatives: [],
};

function makeRequest(url = "http://localhost/service/stripe/og"): Request {
  return new Request(url);
}

async function callServiceOGRoute(slug = "stripe"): Promise<Response> {
  const mod = await import("../app/service/[slug]/og/route");
  return mod.GET(makeRequest() as Parameters<typeof mod.GET>[0], {
    params: Promise.resolve({ slug }),
  });
}

describe("service OG route", () => {
  beforeEach(() => {
    getServiceScoreMock.mockReset();
    getServiceScoreMock.mockResolvedValue(BASE_SCORE);
  });

  it("responds with 200 for known service", async () => {
    const res = await callServiceOGRoute("stripe");
    expect(res.status).toBe(200);
  });

  it("responds with image/png content type", async () => {
    const res = await callServiceOGRoute("stripe");
    expect(res.headers.get("Content-Type")).toBe("image/png");
  });

  it("fetches score for the correct slug", async () => {
    await callServiceOGRoute("stripe");
    expect(getServiceScoreMock).toHaveBeenCalledWith("stripe");
  });

  it("returns 404 for unknown service", async () => {
    getServiceScoreMock.mockResolvedValue(null);
    const res = await callServiceOGRoute("nonexistent-xyz");
    expect(res.status).toBe(404);
  });

  it("returns JSON body on 404", async () => {
    getServiceScoreMock.mockResolvedValue(null);
    const res = await callServiceOGRoute("nonexistent-xyz");
    const body = await res.json() as { error: string };
    expect(body.error).toContain("not found");
  });

  it("renders L4 tier service correctly", async () => {
    getServiceScoreMock.mockResolvedValue({ ...BASE_SCORE, tier: "L4" });
    const res = await callServiceOGRoute("stripe");
    expect(res.status).toBe(200);
    expect(res.headers.get("Content-Type")).toBe("image/png");
  });

  it("renders L3 tier service correctly", async () => {
    getServiceScoreMock.mockResolvedValue({ ...BASE_SCORE, tier: "L3", tierLabel: "Ready" });
    const res = await callServiceOGRoute("resend");
    expect(res.status).toBe(200);
  });

  it("renders L2 tier service correctly", async () => {
    getServiceScoreMock.mockResolvedValue({ ...BASE_SCORE, tier: "L2", tierLabel: "Developing", aggregateRecommendationScore: 5.5 });
    const res = await callServiceOGRoute("mailchimp");
    expect(res.status).toBe(200);
  });

  it("renders L1 tier service correctly", async () => {
    getServiceScoreMock.mockResolvedValue({ ...BASE_SCORE, tier: "L1", tierLabel: "Emerging", aggregateRecommendationScore: 3.0 });
    const res = await callServiceOGRoute("when2meet");
    expect(res.status).toBe(200);
  });

  it("renders service with null scores gracefully", async () => {
    getServiceScoreMock.mockResolvedValue({
      ...BASE_SCORE,
      aggregateRecommendationScore: null,
      executionScore: null,
      accessReadinessScore: null,
      tier: null,
    });
    const res = await callServiceOGRoute("unknown-service");
    expect(res.status).toBe(200);
    expect(res.headers.get("Content-Type")).toBe("image/png");
  });

  it("fetches correct slug passed in params", async () => {
    getServiceScoreMock.mockResolvedValue({ ...BASE_SCORE, serviceSlug: "algolia" });
    await callServiceOGRoute("algolia");
    expect(getServiceScoreMock).toHaveBeenCalledWith("algolia");
  });

  // ── Metadata injection in service page ──

  it("service page generateMetadata includes OG image URL", async () => {
    const pageMod = await import("../app/service/[slug]/page");
    const meta = await pageMod.generateMetadata({
      params: Promise.resolve({ slug: "stripe" }),
    });
    const ogImages = (meta.openGraph as { images?: Array<{ url?: string }> } | undefined)?.images ?? [];
    expect(ogImages[0]?.url).toBe("/service/stripe/og");
  });

  it("service page generateMetadata OG image dimensions are 1200×630", async () => {
    const pageMod = await import("../app/service/[slug]/page");
    const meta = await pageMod.generateMetadata({
      params: Promise.resolve({ slug: "algolia" }),
    });
    const ogImages = (meta.openGraph as { images?: Array<{ width?: number; height?: number }> } | undefined)?.images ?? [];
    expect(ogImages[0]?.width).toBe(1200);
    expect(ogImages[0]?.height).toBe(630);
  });

  it("service page generateMetadata includes canonical URL", async () => {
    const pageMod = await import("../app/service/[slug]/page");
    const meta = await pageMod.generateMetadata({
      params: Promise.resolve({ slug: "stripe" }),
    });
    expect((meta.alternates as { canonical?: string } | undefined)?.canonical).toBe("/service/stripe");
  });

  it("service page generateMetadata slug in canonical matches param", async () => {
    const pageMod = await import("../app/service/[slug]/page");
    const meta = await pageMod.generateMetadata({
      params: Promise.resolve({ slug: "resend" }),
    });
    expect((meta.alternates as { canonical?: string } | undefined)?.canonical).toBe("/service/resend");
  });
});

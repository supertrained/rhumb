import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { getServiceScoreMock, notFoundMock } = vi.hoisted(() => ({
  getServiceScoreMock: vi.fn(),
  notFoundMock: vi.fn()
}));

vi.mock("../lib/api", () => ({
  getServiceScore: getServiceScoreMock
}));

vi.mock("next/navigation", () => ({
  notFound: notFoundMock
}));

async function renderServicePage(slug = "stripe"): Promise<string> {
  const module = await import("../app/service/[slug]/page");
  const page = await module.default({ params: Promise.resolve({ slug }) });
  return renderToStaticMarkup(page);
}

describe("service page", () => {
  beforeEach(() => {
    getServiceScoreMock.mockReset();
    notFoundMock.mockReset();
    notFoundMock.mockImplementation(() => {
      throw new Error("NEXT_NOT_FOUND");
    });
  });

  it("generates baseline metadata", async () => {
    const module = await import("../app/service/[slug]/page");
    const metadata = await module.generateMetadata({ params: Promise.resolve({ slug: "stripe" }) });

    expect(metadata.title).toBe("stripe | Rhumb");
    expect(metadata.description).toContain("stripe");
  });

  it("renders score breakdown, explanation, failures, and alternatives", async () => {
    getServiceScoreMock.mockResolvedValue({
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
      activeFailures: [
        {
          id: "AF-oauth-redirect",
          summary: "Token refresh requires browser redirect in some flows"
        }
      ],
      alternatives: [
        {
          serviceSlug: "square",
          score: 7.4
        }
      ],
      baseUrl: "https://stripe.com",
      docsUrl: "https://docs.stripe.com",
      openapiUrl: null,
      mcpServerUrl: null,
      evidenceTier: "assessed",
      evidenceTierLabel: "Assessed",
      evidenceCount: 0,
      lastEvaluated: "2026-03-05T23:00:00Z"
    });

    const html = await renderServicePage();

    expect(html).toContain("Aggregate AN Score");
    expect(html).toContain("8.9");
    expect(html).toContain("Execution Score");
    expect(html).toContain("9.1");
    expect(html).toContain("Access Readiness Score");
    expect(html).toContain("8.4");
    expect(html).toContain("Agent Native");
    expect(html).toContain("Confidence");
    expect(html).toContain("Reliable payment API");
    expect(html).toContain("Token refresh requires browser redirect in some flows");
    expect(html).toContain("href=\"/service/square\"");
    expect(html).toContain("Official links");
    expect(html).toContain("href=\"/go?to=https%3A%2F%2Fstripe.com&amp;event=provider_click");
    expect(html).toContain("href=\"/go?to=https%3A%2F%2Fdocs.stripe.com&amp;event=docs_click");
    expect(html).toContain("href=\"/methodology\"");
    expect(html).toContain("href=\"/trust\"");
    expect(html).toContain("href=\"/providers#dispute-a-score\"");
    expect(html).toContain("href=\"/go?to=mailto%3Ateam%40supertrained.ai");
    expect(html).toContain("Email evidence about this score");
    expect(html).toContain("square");
    expect(html).toContain("7.4");
    expect(html).toContain("application/ld+json");
    expect(html).toContain('"@type":"SoftwareApplication"');
    expect(html).toContain('"name":"stripe"');
    expect(notFoundMock).not.toHaveBeenCalled();
  });

  it("maps missing services to not-found", async () => {
    getServiceScoreMock.mockResolvedValue(null);

    await expect(renderServicePage("missing-service")).rejects.toThrow("NEXT_NOT_FOUND");
    expect(notFoundMock).toHaveBeenCalledTimes(1);
  });
});

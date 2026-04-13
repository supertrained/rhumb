/**
 * WU 3.1 Slice A — Category landing page tests
 */
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { getCategoriesMock } = vi.hoisted(() => ({
  getCategoriesMock: vi.fn(),
}));

vi.mock("../lib/api", () => ({
  getCategories: getCategoriesMock,
}));

const ALL_CATEGORIES = [
  "payments", "agent-payments", "ai", "analytics", "auth", "calendar",
  "crm", "devops", "email", "search", "social",
];

const MOCK_CATEGORY_DATA = ALL_CATEGORIES.map((slug, i) => ({
  slug,
  serviceCount: 5 + i,
}));

async function renderHub(): Promise<string> {
  const mod = await import("../app/leaderboard/page");
  const page = await mod.default();
  return renderToStaticMarkup(page);
}

describe("leaderboard hub page", () => {
  beforeEach(() => {
    getCategoriesMock.mockReset();
    getCategoriesMock.mockResolvedValue(MOCK_CATEGORY_DATA);
  });

  // ── Static exports ──

  it("ORDERED_SLUGS starts with payments", async () => {
    const { ORDERED_SLUGS } = await import("../lib/categories");
    expect(ORDERED_SLUGS[0]).toBe("payments");
  });

  it("ORDERED_SLUGS contains exactly 10 categories", async () => {
    const { ORDERED_SLUGS } = await import("../lib/categories");
    expect(ORDERED_SLUGS).toHaveLength(11);
  });

  it("ORDERED_SLUGS has remaining categories in alphabetical order", async () => {
    const { ORDERED_SLUGS } = await import("../lib/categories");
    const rest = ORDERED_SLUGS.slice(1);
    const sorted = [...rest].sort();
    expect(rest).toEqual(sorted);
  });

  it("CATEGORY_INFO has all 11 slugs", async () => {
    const { CATEGORY_INFO } = await import("../lib/categories");
    for (const slug of ALL_CATEGORIES) {
      expect(CATEGORY_INFO[slug]).toBeDefined();
    }
  });

  it("each CATEGORY_INFO entry has non-empty name and description", async () => {
    const { CATEGORY_INFO } = await import("../lib/categories");
    for (const slug of ALL_CATEGORIES) {
      const info = CATEGORY_INFO[slug];
      expect(info.name.length).toBeGreaterThan(0);
      expect(info.description.length).toBeGreaterThan(0);
    }
  });

  // ── Metadata ──

  it("exports correct page metadata title and description", async () => {
    const mod = await import("../app/leaderboard/page");
    const meta = mod.metadata;
    expect(meta.title).toBe("Leaderboard | Rhumb");
    expect(meta.description).toContain("90+ categories");
  });

  it("metadata has canonical URL /leaderboard", async () => {
    const mod = await import("../app/leaderboard/page");
    const meta = mod.metadata;
    expect((meta.alternates as { canonical?: string })?.canonical).toBe("/leaderboard");
  });

  // ── Rendered HTML ──

  it("renders a card for every category", async () => {
    const html = await renderHub();
    for (const slug of ALL_CATEGORIES) {
      expect(html).toContain(`/leaderboard/${slug}`);
    }
  });

  it("renders payments card first", async () => {
    const html = await renderHub();
    const paymentsIdx = html.indexOf("/leaderboard/payments");
    const aiIdx = html.indexOf("/leaderboard/ai");
    expect(paymentsIdx).toBeGreaterThanOrEqual(0);
    expect(paymentsIdx).toBeLessThan(aiIdx);
  });

  it("renders service counts from API data", async () => {
    const html = await renderHub();
    // payments has serviceCount=5, so "5 services"
    expect(html).toContain("5 services");
  });

  it("renders 'Explore category' when count is 0", async () => {
    getCategoriesMock.mockResolvedValue([{ slug: "payments", serviceCount: 0 }]);
    const html = await renderHub();
    expect(html).toContain("Explore category");
  });

  it("renders singular 'service' when count is 1", async () => {
    getCategoriesMock.mockResolvedValue([{ slug: "payments", serviceCount: 1 }]);
    const html = await renderHub();
    expect(html).toContain("1 service");
    expect(html).not.toContain("1 services");
  });

  it("renders the page heading", async () => {
    const html = await renderHub();
    expect(html).toContain("<h1");
    expect(html).toContain("Leaderboard");
    expect(html).toContain('href="/trust"');
    expect(html).toContain('href="/methodology"');
    expect(html).toContain('href="/providers#dispute-a-score"');
  });

  it("renders category names (capitalized display names)", async () => {
    const html = await renderHub();
    expect(html).toContain("Payments");
    expect(html).toContain("Analytics");
    expect(html).toContain("DevOps");
  });

  it("renders category descriptions", async () => {
    const html = await renderHub();
    expect(html).toContain("Payment processing");
    expect(html).toContain("Authentication");
  });
});

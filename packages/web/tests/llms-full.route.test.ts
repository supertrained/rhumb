import { readFileSync } from "node:fs";
import { beforeEach, describe, expect, it, vi } from "vitest";

const getServices = vi.fn();
const getCategories = vi.fn();
const getLeaderboard = vi.fn();

vi.mock("../lib/api", () => ({
  getServices,
  getCategories,
  getLeaderboard,
}));

const WEB_LLMS = readFileSync(new URL("../public/llms.txt", import.meta.url), "utf8").trimEnd();

describe("llms-full route", () => {
  beforeEach(() => {
    vi.resetModules();
    getServices.mockReset();
    getCategories.mockReset();
    getLeaderboard.mockReset();

    getServices.mockResolvedValue([
      {
        slug: "resend",
        name: "Resend",
        description: "Email delivery for product and transactional flows",
        category: "email",
      },
      {
        slug: "firecrawl",
        name: "Firecrawl",
        description: "Web extraction and crawling for agents",
        category: "research",
      },
    ]);

    getCategories.mockResolvedValue([
      { slug: "email", serviceCount: 14 },
      { slug: "research", serviceCount: 9 },
    ]);

    getLeaderboard.mockImplementation(async (slug: string) => {
      if (slug === "email") {
        return {
          error: null,
          items: [
            {
              name: "Resend",
              serviceSlug: "resend",
              aggregateRecommendationScore: 8.7,
              executionScore: 8.8,
              accessReadinessScore: 8.4,
              tier: "L4 Native",
            },
          ],
        };
      }

      return {
        error: null,
        items: [
          {
            name: "Firecrawl",
            serviceSlug: "firecrawl",
            aggregateRecommendationScore: 7.9,
            executionScore: 7.8,
            accessReadinessScore: 8.1,
            tier: "L3 Ready",
          },
        ],
      };
    });
  });

  it("extends the canonical llms surface without drifting from current product truth", async () => {
    const mod = await import("../app/llms-full.txt/route");
    const res = await mod.GET();
    const body = await res.text();

    expect(res.status).toBe(200);
    expect(res.headers.get("Content-Type")).toBe("text/plain; charset=utf-8");
    expect(body.startsWith(WEB_LLMS)).toBe(true);
    expect(body).toContain("resolve_capability");
    expect(body).toContain("estimate_capability");
    expect(body).toContain("Public dispute template");
    expect(body).toContain("Dispute response target: 5 business days");
    expect(body).toContain("## Extended llms-full snapshot");
    expect(body).toContain("Current fetched snapshot: 2 services across 2 categories.");
    expect(body).toContain("## Detailed category index (2 fetched categories)");
    expect(body).toContain("/leaderboard/email (14 services)");
    expect(body).toContain("## Detailed scored-service index (2 fetched services)");
    expect(body).toContain("/service/resend");
    expect(body).toContain("### Email (1 ranked in this snapshot)");
    expect(body).toContain("AN Score 8.7 | Execution 8.8 | Access 8.4 | Tier L4 Native");
    expect(body).not.toContain("find_tools");
    expect(body).not.toContain("get_budget_status");
  });
});

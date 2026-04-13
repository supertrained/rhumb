import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { getLaunchDashboardMock, notFoundMock } = vi.hoisted(() => ({
  getLaunchDashboardMock: vi.fn(),
  notFoundMock: vi.fn()
}));

vi.mock("../lib/api", () => ({
  getLaunchDashboard: getLaunchDashboardMock
}));

vi.mock("next/navigation", () => ({
  notFound: notFoundMock
}));

async function renderLaunchPage(searchParams: { key?: string; window?: "24h" | "7d" | "launch" }) {
  const module = await import("../app/internal/launch/page");
  const page = await module.default({ searchParams: Promise.resolve(searchParams) });
  return renderToStaticMarkup(page);
}

describe("internal launch dashboard page", () => {
  beforeEach(() => {
    getLaunchDashboardMock.mockReset();
    notFoundMock.mockReset();
    notFoundMock.mockImplementation(() => {
      throw new Error("NEXT_NOT_FOUND");
    });
    process.env.RHUMB_ADMIN_SECRET = "admin-secret";
    process.env.RHUMB_LAUNCH_DASHBOARD_KEY = "dashboard-key";
  });

  it("renders the dashboard when the key matches", async () => {
    getLaunchDashboardMock.mockResolvedValue({
      window: "7d",
      startAt: "2026-03-06T00:00:00Z",
      generatedAt: "2026-03-13T00:00:00Z",
      coverage: { publicServiceCount: 53 },
      queries: {
        total: 12,
        machineTotal: 7,
        bySource: [{ key: "mcp", count: 5 }],
        topQueryTypes: [{ key: "score_lookup", count: 6 }],
        topServices: [{ key: "stripe", count: 4 }],
        topSearches: [{ key: "payments", count: 2 }],
        uniqueClients: 3,
        repeatClients: 1,
        repeatClientRate: 0.3333,
        latestActivityAt: "2026-03-13T00:00:00Z"
      },
      clicks: {
        total: 4,
        providerClicks: 3,
        topProviderDomains: [{ key: "stripe.com", count: 2 }],
        topSourceSurfaces: [{ key: "service_page", count: 3 }],
        providerCtr: [{ service_slug: "stripe", clicks: 2, views: 4, ctr: 0.5 }],
        disputeClicks: { email: 1, github: 0, contact: 1 },
        latestActivityAt: "2026-03-13T00:00:00Z"
      }
    });

    const html = await renderLaunchPage({ key: "dashboard-key", window: "7d" });

    expect(html).toContain("Launch dashboard");
    expect(html).toContain("Known clients");
    expect(html).toContain("stripe.com");
    expect(html).toContain("provider clicks / 4 service views");
    expect(getLaunchDashboardMock).toHaveBeenCalledWith("7d", "dashboard-key", "dashboard");
    expect(notFoundMock).not.toHaveBeenCalled();
  });

  it("falls back to admin auth when no bounded dashboard key is configured", async () => {
    process.env.RHUMB_LAUNCH_DASHBOARD_KEY = "";
    getLaunchDashboardMock.mockResolvedValue({
      window: "24h",
      startAt: "2026-03-12T00:00:00Z",
      generatedAt: "2026-03-13T00:00:00Z",
      coverage: { publicServiceCount: 1 },
      queries: {
        total: 1,
        machineTotal: 1,
        bySource: [],
        topQueryTypes: [],
        topServices: [],
        topSearches: [],
        uniqueClients: 1,
        repeatClients: 0,
        repeatClientRate: 0,
        latestActivityAt: null,
      },
      clicks: {
        total: 0,
        providerClicks: 0,
        topProviderDomains: [],
        topSourceSurfaces: [],
        providerCtr: [],
        disputeClicks: { email: 0, github: 0, contact: 0 },
        latestActivityAt: null,
      },
    });

    const html = await renderLaunchPage({ key: "admin-secret", window: "24h" });

    expect(html).toContain("Launch dashboard");
    expect(getLaunchDashboardMock).toHaveBeenCalledWith("24h", "admin-secret", "admin");
    expect(notFoundMock).not.toHaveBeenCalled();
  });

  it("rejects requests without the internal key", async () => {
    getLaunchDashboardMock.mockResolvedValue(null);

    await expect(renderLaunchPage({ key: "wrong-key", window: "7d" })).rejects.toThrow("NEXT_NOT_FOUND");
    expect(notFoundMock).toHaveBeenCalledTimes(1);
  });
});

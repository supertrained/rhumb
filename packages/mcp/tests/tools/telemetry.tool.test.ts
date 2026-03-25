import { describe, it, expect, vi } from "vitest";
import { handleUsageTelemetry } from "../../src/tools/telemetry.js";
import type { RhumbApiClient, UsageTelemetryResult } from "../../src/api-client.js";

const telemetryResult: UsageTelemetryResult = {
  agent_id: "agent_test",
  period_days: 7,
  summary: {
    total_calls: 12,
    successful_calls: 11,
    failed_calls: 1,
    total_cost_usd: 0.42,
    avg_latency_ms: 340.2,
    p50_latency_ms: 280,
    p95_latency_ms: 890
  },
  by_capability: [
    {
      capability_id: "search.web_search",
      calls: 12,
      success_rate: 0.917,
      avg_latency_ms: 340.2,
      total_cost_usd: 0.42,
      top_provider: "tavily"
    }
  ],
  by_provider: [
    {
      provider: "tavily",
      calls: 10,
      success_rate: 1,
      avg_latency_ms: 300,
      total_cost_usd: 0.3,
      error_rate: 0,
      avg_upstream_latency_ms: 280
    },
    {
      provider: "serpapi",
      calls: 2,
      success_rate: 0.5,
      avg_latency_ms: 541,
      total_cost_usd: 0.12,
      error_rate: 0.5,
      avg_upstream_latency_ms: 500
    }
  ],
  by_time: [
    { period: "2026-03-24", calls: 7, success_rate: 1, avg_latency_ms: 280 },
    { period: "2026-03-25", calls: 5, success_rate: 0.8, avg_latency_ms: 420 }
  ]
};

function createMockClient(result: UsageTelemetryResult = telemetryResult): RhumbApiClient {
  return {
    searchServices: vi.fn().mockResolvedValue([]),
    getServiceScore: vi.fn().mockResolvedValue(null),
    discoverCapabilities: vi.fn().mockResolvedValue({ items: [], total: 0 }),
    resolveCapability: vi.fn().mockResolvedValue(null),
    executeCapability: vi.fn().mockResolvedValue({ capabilityId: "", providerUsed: "", credentialMode: "byo", upstreamStatus: 200, upstreamResponse: {}, costEstimateUsd: null, latencyMs: null, fallbackAttempted: false, fallbackProvider: null, executionId: "exec_test" }),
    estimateCapability: vi.fn().mockResolvedValue({ capabilityId: "", provider: "", credentialMode: "byo", costEstimateUsd: null, circuitState: "closed", endpointPattern: null }),
    listCeremonies: vi.fn().mockResolvedValue([]),
    getCeremony: vi.fn().mockResolvedValue(null),
    listManagedCapabilities: vi.fn().mockResolvedValue([]),
    getBudget: vi.fn().mockResolvedValue({ unlimited: true }),
    setBudget: vi.fn().mockResolvedValue({}),
    getSpend: vi.fn().mockResolvedValue({ total_spend_usd: 0, total_executions: 0, by_capability: [], by_provider: [] }),
    getRoutingStrategy: vi.fn().mockResolvedValue({ strategy: "balanced", quality_floor: 6.0 }),
    setRoutingStrategy: vi.fn().mockResolvedValue({}),
    getUsageTelemetry: vi.fn().mockResolvedValue(result),
    getBalance: vi.fn().mockResolvedValue({ balance_usd: 25, balance_usd_cents: 2500, auto_reload_enabled: false }),
    createCheckout: vi.fn().mockResolvedValue({ checkout_url: "https://checkout.stripe.com/test", session_id: "cs_test" }),
    getLedger: vi.fn().mockResolvedValue({ entries: [], total_count: 0 }),
  };
}

describe("usage_telemetry handler", () => {
  it("returns a formatted telemetry summary", async () => {
    const client = createMockClient();
    const result = await handleUsageTelemetry({ days: 7 }, client);

    expect(client.getUsageTelemetry).toHaveBeenCalledWith({
      days: 7,
      capability_id: undefined,
      provider: undefined
    });
    expect(result.agent_id).toBe("agent_test");
    expect(result.top_capability).toBe("search.web_search");
    expect(result.top_provider).toBe("tavily");
    expect(result.provider_health[0]).toEqual({
      provider: "tavily",
      status: "healthy",
      success_rate: 1,
      avg_latency_ms: 300,
      calls: 10
    });
  });

  it("maps weaker provider success rates to degraded or unhealthy status", async () => {
    const client = createMockClient();
    const result = await handleUsageTelemetry({}, client);

    expect(result.provider_health[1].provider).toBe("serpapi");
    expect(result.provider_health[1].status).toBe("unhealthy");
  });

  it("returns a non-throwing error payload on client failure", async () => {
    const client = createMockClient();
    (client.getUsageTelemetry as ReturnType<typeof vi.fn>).mockRejectedValue(new Error("401"));

    const result = await handleUsageTelemetry({}, client);

    expect(result.agent_id).toBe("");
    expect(result.summary.total_calls).toBe(0);
    expect(result.message).toContain("Failed to fetch usage telemetry");
  });
});

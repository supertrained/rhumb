import { describe, it, expect, vi } from "vitest";
import { handleFindServices } from "../../src/tools/find.js";
import type { RhumbApiClient, ServiceSearchItem } from "../../src/api-client.js";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const mockServices: ServiceSearchItem[] = [
  {
    name: "SendGrid",
    slug: "sendgrid",
    aggregateScore: 82,
    executionScore: 85,
    accessScore: 79,
    explanation: "Reliable email API with strong SDK support"
  },
  {
    name: "Mailgun",
    slug: "mailgun",
    aggregateScore: 78,
    executionScore: 80,
    accessScore: 76,
    explanation: "Good email delivery with flexible pricing"
  },
  {
    name: "Resend",
    slug: "resend",
    aggregateScore: 91,
    executionScore: 93,
    accessScore: 89,
    explanation: "Modern email API with excellent DX"
  },
  {
    name: "Postmark",
    slug: "postmark",
    aggregateScore: 85,
    executionScore: 88,
    accessScore: 82,
    explanation: "Fast transactional email delivery"
  },
  {
    name: "Experimental Mail",
    slug: "experimental-mail",
    aggregateScore: null,
    executionScore: null,
    accessScore: null,
    explanation: "New service, not yet scored"
  }
];

function createMockClient(
  services: ServiceSearchItem[] = mockServices
): RhumbApiClient {
  return {
    searchServices: vi.fn().mockResolvedValue(services),
    getServiceScore: vi.fn().mockResolvedValue(null),
    discoverCapabilities: vi.fn().mockResolvedValue({ items: [], total: 0 }),
    resolveCapability: vi.fn(),
    executeCapability: vi.fn().mockResolvedValue({ capabilityId: "", providerUsed: "", credentialMode: "byo", upstreamStatus: 200, upstreamResponse: {}, costEstimateUsd: null, latencyMs: null, fallbackAttempted: false, fallbackProvider: null, executionId: "exec_test" }),
    estimateCapability: vi.fn().mockResolvedValue({ capabilityId: "", provider: "", credentialMode: "byo", costEstimateUsd: null, circuitState: "closed", endpointPattern: null }).mockResolvedValue({ capability: "", providers: [], fallback_chain: [] }),
    listCeremonies: vi.fn().mockResolvedValue([]),
    getCeremony: vi.fn().mockResolvedValue(null),
    listManagedCapabilities: vi.fn().mockResolvedValue([]),
    getBudget: vi.fn().mockResolvedValue({ unlimited: true }),
    setBudget: vi.fn().mockResolvedValue({}),
    getSpend: vi.fn().mockResolvedValue({ total_spend_usd: 0, total_executions: 0, by_capability: [], by_provider: [] }),
    getRoutingStrategy: vi.fn().mockResolvedValue({ strategy: "balanced", quality_floor: 6.0 }),
    setRoutingStrategy: vi.fn().mockResolvedValue({}),
    getUsageTelemetry: vi.fn().mockResolvedValue({ agent_id: "", period_days: 7, summary: { total_calls: 0, successful_calls: 0, failed_calls: 0, total_cost_usd: 0, avg_latency_ms: 0, p50_latency_ms: 0, p95_latency_ms: 0 }, by_capability: [], by_provider: [], by_time: [] }),
    getBalance: vi.fn().mockResolvedValue({ balance_usd: 25, balance_usd_cents: 2500, auto_reload_enabled: false }),
    createCheckout: vi.fn().mockResolvedValue({ checkout_url: 'https://checkout.stripe.com/test', session_id: 'cs_test' }),
    getLedger: vi.fn().mockResolvedValue({ entries: [], total_count: 0 }),
  };
}

function createErrorClient(): RhumbApiClient {
  return {
    searchServices: vi.fn().mockRejectedValue(new Error("Network failure")),
    getServiceScore: vi.fn().mockRejectedValue(new Error("Network failure")),
    discoverCapabilities: vi.fn().mockResolvedValue({ items: [], total: 0 }),
    resolveCapability: vi.fn(),
    executeCapability: vi.fn().mockResolvedValue({ capabilityId: "", providerUsed: "", credentialMode: "byo", upstreamStatus: 200, upstreamResponse: {}, costEstimateUsd: null, latencyMs: null, fallbackAttempted: false, fallbackProvider: null, executionId: "exec_test" }),
    estimateCapability: vi.fn().mockResolvedValue({ capabilityId: "", provider: "", credentialMode: "byo", costEstimateUsd: null, circuitState: "closed", endpointPattern: null }).mockResolvedValue({ capability: "", providers: [], fallback_chain: [] }),
    listCeremonies: vi.fn().mockResolvedValue([]),
    getCeremony: vi.fn().mockResolvedValue(null),
    listManagedCapabilities: vi.fn().mockResolvedValue([]),
    getBudget: vi.fn().mockResolvedValue({ unlimited: true }),
    setBudget: vi.fn().mockResolvedValue({}),
    getSpend: vi.fn().mockResolvedValue({ total_spend_usd: 0, total_executions: 0, by_capability: [], by_provider: [] }),
    getRoutingStrategy: vi.fn().mockResolvedValue({ strategy: "balanced", quality_floor: 6.0 }),
    setRoutingStrategy: vi.fn().mockResolvedValue({}),
    getUsageTelemetry: vi.fn().mockResolvedValue({ agent_id: "", period_days: 7, summary: { total_calls: 0, successful_calls: 0, failed_calls: 0, total_cost_usd: 0, avg_latency_ms: 0, p50_latency_ms: 0, p95_latency_ms: 0 }, by_capability: [], by_provider: [], by_time: [] }),
    getBalance: vi.fn().mockResolvedValue({ balance_usd: 25, balance_usd_cents: 2500, auto_reload_enabled: false }),
    createCheckout: vi.fn().mockResolvedValue({ checkout_url: 'https://checkout.stripe.com/test', session_id: 'cs_test' }),
    getLedger: vi.fn().mockResolvedValue({ entries: [], total_count: 0 }),
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("find_services handler", () => {
  it("returns results ranked by aggregateScore descending", async () => {
    const client = createMockClient();
    const result = await handleFindServices({ query: "email" }, client);

    expect(result.services.length).toBeGreaterThan(0);
    expect(client.searchServices).toHaveBeenCalledWith("email");

    // Verify descending order (nulls at end)
    for (let i = 0; i < result.services.length - 1; i++) {
      const current = result.services[i].aggregateScore;
      const next = result.services[i + 1].aggregateScore;
      if (current !== null && next !== null) {
        expect(current).toBeGreaterThanOrEqual(next);
      }
      if (current === null) {
        expect(next).toBeNull();
      }
    }

    // First result should be highest scored
    expect(result.services[0].slug).toBe("resend");
    expect(result.services[0].aggregateScore).toBe(91);
  });

  it("clamps limit to MAX_LIMIT (50) and MIN (1)", async () => {
    const client = createMockClient();

    // Limit = 2 should return only 2
    const result = await handleFindServices({ query: "email", limit: 2 }, client);
    expect(result.services).toHaveLength(2);
    expect(result.services[0].slug).toBe("resend");
    expect(result.services[1].slug).toBe("postmark");

    // Limit = 0 should clamp to 1
    const result2 = await handleFindServices({ query: "email", limit: 0 }, client);
    expect(result2.services).toHaveLength(1);

    // Limit = 100 should clamp to 50 (but we only have 5 items)
    const result3 = await handleFindServices({ query: "email", limit: 100 }, client);
    expect(result3.services).toHaveLength(5);
  });

  it("defaults limit to 10 when not provided", async () => {
    const client = createMockClient();
    const result = await handleFindServices({ query: "email" }, client);

    // We have 5 items, default limit is 10, so all 5 returned
    expect(result.services).toHaveLength(5);
    expect(client.searchServices).toHaveBeenCalledWith("email");
  });

  it("returns empty array when API returns no results", async () => {
    const client = createMockClient([]);
    const result = await handleFindServices({ query: "nonexistent" }, client);

    expect(result.services).toEqual([]);
    expect(client.searchServices).toHaveBeenCalledWith("nonexistent");
  });

  it("returns empty array on API error (resilient fallback)", async () => {
    const client = createErrorClient();
    const result = await handleFindServices({ query: "email" }, client);

    expect(result.services).toEqual([]);
  });

  it("includes all required output fields per tool", async () => {
    const client = createMockClient();
    const result = await handleFindServices({ query: "email", limit: 1 }, client);

    const service = result.services[0];
    expect(service).toHaveProperty("name");
    expect(service).toHaveProperty("slug");
    expect(service).toHaveProperty("aggregateScore");
    expect(service).toHaveProperty("executionScore");
    expect(service).toHaveProperty("accessScore");
    expect(service).toHaveProperty("explanation");
  });

  it("null scores sort to the end", async () => {
    const client = createMockClient();
    const result = await handleFindServices({ query: "email" }, client);

    // "experimental-mail" has null score — should be last
    const lastService = result.services[result.services.length - 1];
    expect(lastService.slug).toBe("experimental-mail");
    expect(lastService.aggregateScore).toBeNull();
  });
});

import { describe, it, expect, vi } from "vitest";
import { handleGetScore } from "../../src/tools/score.js";
import type { RhumbApiClient, ServiceScoreItem } from "../../src/api-client.js";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const mockScoreResponse: ServiceScoreItem = {
  slug: "sendgrid",
  aggregateScore: 82,
  executionScore: 85,
  accessScore: 79,
  confidence: 0.95,
  tier: "ready",
  explanation: "Reliable email API with strong SDK support and mature documentation",
  freshness: "2026-03-01T00:00:00Z",
  failureModes: [],
  tags: []
};

function createMockClient(
  score: ServiceScoreItem | null = mockScoreResponse
): RhumbApiClient {
  return {
    searchServices: vi.fn().mockResolvedValue([]),
    getServiceScore: vi.fn().mockResolvedValue(score),
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
  };
}

function createErrorClient(): RhumbApiClient {
  return {
    searchServices: vi.fn().mockResolvedValue([]),
    getServiceScore: vi.fn().mockRejectedValue(new Error("API returned 500")),
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
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("get_score handler", () => {
  it("returns full score breakdown for a valid slug", async () => {
    const client = createMockClient();
    const result = await handleGetScore({ slug: "sendgrid" }, client);

    expect(client.getServiceScore).toHaveBeenCalledWith("sendgrid");
    expect(result).toEqual({
      slug: "sendgrid",
      aggregateScore: 82,
      executionScore: 85,
      accessScore: 79,
      confidence: 0.95,
      tier: "ready",
      explanation: "Reliable email API with strong SDK support and mature documentation",
      freshness: "2026-03-01T00:00:00Z",
      failureModes: [],
      tags: []
    });
  });

  it("includes all required output fields", async () => {
    const client = createMockClient();
    const result = await handleGetScore({ slug: "sendgrid" }, client);

    expect(result).toHaveProperty("slug");
    expect(result).toHaveProperty("aggregateScore");
    expect(result).toHaveProperty("executionScore");
    expect(result).toHaveProperty("accessScore");
    expect(result).toHaveProperty("confidence");
    expect(result).toHaveProperty("tier");
    expect(result).toHaveProperty("explanation");
    expect(result).toHaveProperty("freshness");
  });

  it("returns error response for 404 (service not found)", async () => {
    const client = createMockClient(null);
    const result = await handleGetScore({ slug: "nonexistent-service" }, client);

    expect(result.slug).toBe("nonexistent-service");
    expect(result.aggregateScore).toBeNull();
    expect(result.executionScore).toBeNull();
    expect(result.accessScore).toBeNull();
    expect(result.confidence).toBe(0);
    expect(result.tier).toBe("unknown");
    expect(result.explanation).toContain("nonexistent-service");
    expect(result.explanation).toContain("not found");
    expect(result.freshness).toBe("unknown");
  });

  it("returns error response on API error (resilient fallback)", async () => {
    const client = createErrorClient();
    const result = await handleGetScore({ slug: "sendgrid" }, client);

    expect(result.slug).toBe("sendgrid");
    expect(result.aggregateScore).toBeNull();
    expect(result.confidence).toBe(0);
    expect(result.tier).toBe("unknown");
    expect(result.explanation).toContain("Failed to fetch score");
    expect(result.explanation).toContain("API returned 500");
    expect(result.freshness).toBe("unknown");
  });

  it("does not throw on API error", async () => {
    const client = createErrorClient();

    // Should not throw — returns error response instead
    await expect(
      handleGetScore({ slug: "sendgrid" }, client)
    ).resolves.toBeDefined();
  });
});

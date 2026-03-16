import { describe, it, expect, vi } from "vitest";
import { handleGetFailureModes } from "../../src/tools/failures.js";
import type {
  RhumbApiClient,
  ServiceScoreItem,
  FailureModeItem
} from "../../src/api-client.js";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const mockFailureModes: FailureModeItem[] = [
  {
    pattern: "Rate limit exceeded on burst sends",
    impact: "Emails delayed or silently dropped during peak traffic",
    frequency: "moderate",
    workaround: "Implement exponential backoff with jitter",
    tags: ["rate-limiting", "email-delivery"]
  },
  {
    pattern: "Webhook delivery failure on HTTPS endpoints",
    impact: "Lost event notifications for bounces and opens",
    frequency: "low",
    workaround: "Use polling as fallback; configure retry policy",
    tags: ["webhooks"]
  },
  {
    pattern: "API key rotation causes temporary auth failures",
    impact: "503 errors during key propagation window (~30s)",
    frequency: "rare",
    workaround: "Support dual active keys during rotation",
    tags: ["auth", "key-management"]
  }
];

const mockScoreWithFailures: ServiceScoreItem = {
  slug: "sendgrid",
  aggregateScore: 82,
  executionScore: 85,
  accessScore: 79,
  confidence: 0.95,
  tier: "ready",
  explanation: "Reliable email API",
  freshness: "2026-03-01T00:00:00Z",
  failureModes: mockFailureModes,
  tags: ["rate-limiting", "email-delivery", "webhooks", "auth", "key-management"]
};

function createMockClient(
  score: ServiceScoreItem | null = mockScoreWithFailures
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
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("get_failure_modes handler", () => {
  it("extracts and maps failure modes from score response", async () => {
    const client = createMockClient();
    const result = await handleGetFailureModes({ slug: "sendgrid" }, client);

    expect(client.getServiceScore).toHaveBeenCalledWith("sendgrid");
    expect(result.failures).toHaveLength(3);

    expect(result.failures[0]).toEqual({
      pattern: "Rate limit exceeded on burst sends",
      impact: "Emails delayed or silently dropped during peak traffic",
      frequency: "moderate",
      workaround: "Implement exponential backoff with jitter"
    });

    expect(result.failures[1]).toEqual({
      pattern: "Webhook delivery failure on HTTPS endpoints",
      impact: "Lost event notifications for bounces and opens",
      frequency: "low",
      workaround: "Use polling as fallback; configure retry policy"
    });

    expect(result.failures[2]).toEqual({
      pattern: "API key rotation causes temporary auth failures",
      impact: "503 errors during key propagation window (~30s)",
      frequency: "rare",
      workaround: "Support dual active keys during rotation"
    });
  });

  it("includes all required output fields per failure mode", async () => {
    const client = createMockClient();
    const result = await handleGetFailureModes({ slug: "sendgrid" }, client);

    for (const failure of result.failures) {
      expect(failure).toHaveProperty("pattern");
      expect(failure).toHaveProperty("impact");
      expect(failure).toHaveProperty("frequency");
      expect(failure).toHaveProperty("workaround");
      expect(typeof failure.pattern).toBe("string");
      expect(typeof failure.impact).toBe("string");
      expect(typeof failure.frequency).toBe("string");
      expect(typeof failure.workaround).toBe("string");
    }
  });

  it("does not include internal tags in the output", async () => {
    const client = createMockClient();
    const result = await handleGetFailureModes({ slug: "sendgrid" }, client);

    for (const failure of result.failures) {
      expect(failure).not.toHaveProperty("tags");
    }
  });

  it("returns empty array when service has no failure modes", async () => {
    const scoreNoFailures: ServiceScoreItem = {
      ...mockScoreWithFailures,
      failureModes: [],
      tags: []
    };
    const client = createMockClient(scoreNoFailures);
    const result = await handleGetFailureModes({ slug: "sendgrid" }, client);

    expect(result.failures).toEqual([]);
  });

  it("returns empty array when service is not found (404)", async () => {
    const client = createMockClient(null);
    const result = await handleGetFailureModes({ slug: "nonexistent" }, client);

    expect(result.failures).toEqual([]);
  });

  it("returns empty array on API error (resilient fallback)", async () => {
    const client = createErrorClient();
    const result = await handleGetFailureModes({ slug: "sendgrid" }, client);

    expect(result.failures).toEqual([]);
  });

  it("does not throw on API error", async () => {
    const client = createErrorClient();

    await expect(
      handleGetFailureModes({ slug: "sendgrid" }, client)
    ).resolves.toBeDefined();
  });
});

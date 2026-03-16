import { describe, it, expect, vi } from "vitest";
import { handleFindTools } from "../../src/tools/find.js";
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
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("find_tools handler", () => {
  it("returns results ranked by aggregateScore descending", async () => {
    const client = createMockClient();
    const result = await handleFindTools({ query: "email" }, client);

    expect(result.tools.length).toBeGreaterThan(0);
    expect(client.searchServices).toHaveBeenCalledWith("email");

    // Verify descending order (nulls at end)
    for (let i = 0; i < result.tools.length - 1; i++) {
      const current = result.tools[i].aggregateScore;
      const next = result.tools[i + 1].aggregateScore;
      if (current !== null && next !== null) {
        expect(current).toBeGreaterThanOrEqual(next);
      }
      if (current === null) {
        expect(next).toBeNull();
      }
    }

    // First result should be highest scored
    expect(result.tools[0].slug).toBe("resend");
    expect(result.tools[0].aggregateScore).toBe(91);
  });

  it("clamps limit to MAX_LIMIT (50) and MIN (1)", async () => {
    const client = createMockClient();

    // Limit = 2 should return only 2
    const result = await handleFindTools({ query: "email", limit: 2 }, client);
    expect(result.tools).toHaveLength(2);
    expect(result.tools[0].slug).toBe("resend");
    expect(result.tools[1].slug).toBe("postmark");

    // Limit = 0 should clamp to 1
    const result2 = await handleFindTools({ query: "email", limit: 0 }, client);
    expect(result2.tools).toHaveLength(1);

    // Limit = 100 should clamp to 50 (but we only have 5 items)
    const result3 = await handleFindTools({ query: "email", limit: 100 }, client);
    expect(result3.tools).toHaveLength(5);
  });

  it("defaults limit to 10 when not provided", async () => {
    const client = createMockClient();
    const result = await handleFindTools({ query: "email" }, client);

    // We have 5 items, default limit is 10, so all 5 returned
    expect(result.tools).toHaveLength(5);
    expect(client.searchServices).toHaveBeenCalledWith("email");
  });

  it("returns empty array when API returns no results", async () => {
    const client = createMockClient([]);
    const result = await handleFindTools({ query: "nonexistent" }, client);

    expect(result.tools).toEqual([]);
    expect(client.searchServices).toHaveBeenCalledWith("nonexistent");
  });

  it("returns empty array on API error (resilient fallback)", async () => {
    const client = createErrorClient();
    const result = await handleFindTools({ query: "email" }, client);

    expect(result.tools).toEqual([]);
  });

  it("includes all required output fields per tool", async () => {
    const client = createMockClient();
    const result = await handleFindTools({ query: "email", limit: 1 }, client);

    const tool = result.tools[0];
    expect(tool).toHaveProperty("name");
    expect(tool).toHaveProperty("slug");
    expect(tool).toHaveProperty("aggregateScore");
    expect(tool).toHaveProperty("executionScore");
    expect(tool).toHaveProperty("accessScore");
    expect(tool).toHaveProperty("explanation");
  });

  it("null scores sort to the end", async () => {
    const client = createMockClient();
    const result = await handleFindTools({ query: "email" }, client);

    // "experimental-mail" has null score — should be last
    const lastTool = result.tools[result.tools.length - 1];
    expect(lastTool.slug).toBe("experimental-mail");
    expect(lastTool.aggregateScore).toBeNull();
  });
});

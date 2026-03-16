import { describe, it, expect, vi } from "vitest";
import { handleGetAlternatives } from "../../src/tools/alternatives.js";
import type {
  RhumbApiClient,
  ServiceScoreItem,
  ServiceSearchItem
} from "../../src/api-client.js";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const mockScoreWithTags: ServiceScoreItem = {
  slug: "sendgrid",
  aggregateScore: 72,
  executionScore: 75,
  accessScore: 69,
  confidence: 0.9,
  tier: "ready",
  explanation: "Reliable but aging email API",
  freshness: "2026-03-01T00:00:00Z",
  failureModes: [
    {
      pattern: "Rate limit exceeded",
      impact: "Emails delayed or dropped",
      frequency: "moderate",
      workaround: "Implement exponential backoff",
      tags: ["rate-limiting", "email-delivery"]
    },
    {
      pattern: "Webhook delivery failure",
      impact: "Lost event notifications",
      frequency: "low",
      workaround: "Use polling as fallback",
      tags: ["webhooks"]
    }
  ],
  tags: ["rate-limiting", "email-delivery", "webhooks"]
};

const peerServices: ServiceSearchItem[] = [
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
    name: "Mailgun",
    slug: "mailgun",
    aggregateScore: 68,
    executionScore: 70,
    accessScore: 66,
    explanation: "Flexible email with lower score"
  },
  {
    name: "SendGrid",
    slug: "sendgrid",
    aggregateScore: 72,
    executionScore: 75,
    accessScore: 69,
    explanation: "The service itself (should be excluded)"
  }
];

function createMockClient(
  score: ServiceScoreItem | null = mockScoreWithTags,
  searchResults: ServiceSearchItem[] = peerServices
): RhumbApiClient {
  return {
    searchServices: vi.fn().mockResolvedValue(searchResults),
    getServiceScore: vi.fn().mockResolvedValue(score),
    discoverCapabilities: vi.fn().mockResolvedValue({ items: [], total: 0 }),
    resolveCapability: vi.fn().mockResolvedValue({ capability: "", providers: [], fallback_chain: [] }),
  };
}

function createErrorClient(): RhumbApiClient {
  return {
    searchServices: vi.fn().mockRejectedValue(new Error("Network failure")),
    getServiceScore: vi.fn().mockRejectedValue(new Error("Network failure")),
    discoverCapabilities: vi.fn().mockResolvedValue({ items: [], total: 0 }),
    resolveCapability: vi.fn().mockResolvedValue({ capability: "", providers: [], fallback_chain: [] }),
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("get_alternatives handler", () => {
  it("returns alternatives ranked by aggregateScore descending", async () => {
    const client = createMockClient();
    const result = await handleGetAlternatives({ slug: "sendgrid" }, client);

    expect(client.getServiceScore).toHaveBeenCalledWith("sendgrid");
    expect(result.alternatives.length).toBeGreaterThan(0);

    // Verify descending order
    for (let i = 0; i < result.alternatives.length - 1; i++) {
      const current = result.alternatives[i].aggregateScore ?? 0;
      const next = result.alternatives[i + 1].aggregateScore ?? 0;
      expect(current).toBeGreaterThanOrEqual(next);
    }

    // First alternative should be highest-scored peer
    expect(result.alternatives[0].slug).toBe("resend");
    expect(result.alternatives[0].aggregateScore).toBe(91);
  });

  it("only includes peers with higher aggregateScore than the current service", async () => {
    const client = createMockClient();
    const result = await handleGetAlternatives({ slug: "sendgrid" }, client);

    // sendgrid has score 72 — only resend (91) and postmark (85) should appear
    // mailgun (68) is lower, sendgrid itself is excluded
    const slugs = result.alternatives.map((a) => a.slug);
    expect(slugs).toContain("resend");
    expect(slugs).toContain("postmark");
    expect(slugs).not.toContain("mailgun");
    expect(slugs).not.toContain("sendgrid");
  });

  it("excludes the current service from alternatives", async () => {
    const client = createMockClient();
    const result = await handleGetAlternatives({ slug: "sendgrid" }, client);

    const slugs = result.alternatives.map((a) => a.slug);
    expect(slugs).not.toContain("sendgrid");
  });

  it("deduplicates peers found across multiple tag searches", async () => {
    // The service has 3 tags, so searchServices is called 3 times
    // Each call returns the same peers — should be deduplicated
    const client = createMockClient();
    const result = await handleGetAlternatives({ slug: "sendgrid" }, client);

    const slugs = result.alternatives.map((a) => a.slug);
    const uniqueSlugs = new Set(slugs);
    expect(slugs.length).toBe(uniqueSlugs.size);
  });

  it("includes reason with shared failure pattern tags", async () => {
    const client = createMockClient();
    const result = await handleGetAlternatives({ slug: "sendgrid" }, client);

    for (const alt of result.alternatives) {
      expect(alt.reason).toContain("shared failure patterns");
      expect(alt).toHaveProperty("name");
      expect(alt).toHaveProperty("slug");
      expect(alt).toHaveProperty("aggregateScore");
    }
  });

  it("returns empty array when service has no failure tags", async () => {
    const scoreNoTags: ServiceScoreItem = {
      ...mockScoreWithTags,
      failureModes: [],
      tags: []
    };
    const client = createMockClient(scoreNoTags);
    const result = await handleGetAlternatives({ slug: "sendgrid" }, client);

    expect(result.alternatives).toEqual([]);
  });

  it("returns empty array when service is not found (404)", async () => {
    const client = createMockClient(null);
    const result = await handleGetAlternatives({ slug: "nonexistent" }, client);

    expect(result.alternatives).toEqual([]);
  });

  it("returns empty array on API error (resilient fallback)", async () => {
    const client = createErrorClient();
    const result = await handleGetAlternatives({ slug: "sendgrid" }, client);

    expect(result.alternatives).toEqual([]);
  });

  it("returns empty array when no peers have higher scores", async () => {
    // All peers have lower scores than the current service
    const highScore: ServiceScoreItem = {
      ...mockScoreWithTags,
      aggregateScore: 99
    };
    const client = createMockClient(highScore);
    const result = await handleGetAlternatives({ slug: "sendgrid" }, client);

    expect(result.alternatives).toEqual([]);
  });
});

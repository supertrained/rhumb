/**
 * End-to-end integration tests for the Rhumb MCP Server.
 *
 * These tests create a real MCP server instance via createServer() with a
 * mock API client, then invoke each registered tool through the server's
 * internal handler pipeline — verifying the full registration → dispatch →
 * handler → response chain.
 */

import { describe, it, expect, vi } from "vitest";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { InMemoryTransport } from "@modelcontextprotocol/sdk/inMemory.js";
import { CallToolResultSchema } from "@modelcontextprotocol/sdk/types.js";
import { createServer } from "../src/server.js";
import type {
  RhumbApiClient,
  ServiceSearchItem,
  ServiceScoreItem,
} from "../src/api-client.js";
import type { FindToolOutput, GetScoreOutput, GetAlternativesOutput, GetFailureModesOutput } from "../src/types.js";

// ---------------------------------------------------------------------------
// Mock API client fixtures
// ---------------------------------------------------------------------------

const mockServices: ServiceSearchItem[] = [
  {
    name: "Resend",
    slug: "resend",
    aggregateScore: 91,
    executionScore: 93,
    accessScore: 89,
    explanation: "Modern email API with excellent DX",
  },
  {
    name: "Postmark",
    slug: "postmark",
    aggregateScore: 85,
    executionScore: 88,
    accessScore: 82,
    explanation: "Fast transactional email delivery",
  },
  {
    name: "SendGrid",
    slug: "sendgrid",
    aggregateScore: 72,
    executionScore: 75,
    accessScore: 69,
    explanation: "Reliable email API",
  },
];

const mockScore: ServiceScoreItem = {
  slug: "resend",
  aggregateScore: 91,
  executionScore: 93,
  accessScore: 89,
  confidence: 0.97,
  tier: "excellent",
  explanation: "Modern email API with excellent DX",
  freshness: "2026-03-01T00:00:00Z",
  failureModes: [
    {
      pattern: "SDK timeout on large batch sends",
      impact: "Batch emails may fail silently above 500 recipients",
      frequency: "low",
      workaround: "Split batches into chunks of 100",
      tags: ["batch-sending", "timeout"],
    },
  ],
  tags: ["batch-sending", "timeout"],
};

function createMockApiClient(): RhumbApiClient {
  return {
    searchServices: vi.fn().mockResolvedValue(mockServices),
    getServiceScore: vi.fn().mockImplementation(async (slug: string) => {
      if (slug === "resend") return mockScore;
      if (slug === "nonexistent") return null;
      return { ...mockScore, slug };
    }),
    discoverCapabilities: vi.fn().mockResolvedValue({
      items: [
        {
          id: "email.send",
          domain: "email",
          action: "send",
          description: "Send transactional or marketing email",
          inputHint: "recipient, subject, body",
          outcome: "Email delivered",
          providerCount: 3,
          topProvider: { slug: "resend", anScore: 91, tierLabel: "Excellent" }
        }
      ],
      total: 1
    }),
    resolveCapability: vi.fn().mockResolvedValue({
      capability: "email.send",
      providers: [
        {
          serviceSlug: "resend",
          serviceName: "Resend",
          anScore: 91,
          costPerCall: null,
          freeTierCalls: 100,
          authMethod: "api_key",
          endpointPattern: "POST /emails",
          recommendation: "preferred",
          recommendationReason: "High AN score (91), 100 free calls/month"
        }
      ],
      fallbackChain: ["resend", "sendgrid"],
      relatedBundles: []
    }),
    executeCapability: vi.fn().mockResolvedValue({
      capabilityId: "email.send",
      providerUsed: "resend",
      credentialMode: "byo",
      upstreamStatus: 200,
      upstreamResponse: { id: "msg_123" },
      costEstimateUsd: null,
      latencyMs: 142,
      fallbackAttempted: false,
      fallbackProvider: null,
      executionId: "exec_test123"
    }),
    estimateCapability: vi.fn().mockResolvedValue({
      capabilityId: "email.send",
      provider: "resend",
      credentialMode: "byo",
      costEstimateUsd: null,
      circuitState: "closed",
      endpointPattern: "POST /emails"
    }),
  };
}

function createErrorApiClient(): RhumbApiClient {
  return {
    searchServices: vi
      .fn()
      .mockRejectedValue(new Error("API connection refused")),
    getServiceScore: vi
      .fn()
      .mockRejectedValue(new Error("API connection refused")),
    discoverCapabilities: vi
      .fn()
      .mockRejectedValue(new Error("API connection refused")),
    resolveCapability: vi
      .fn()
      .mockRejectedValue(new Error("API connection refused")),
    executeCapability: vi
      .fn()
      .mockRejectedValue(new Error("API connection refused")),
    estimateCapability: vi
      .fn()
      .mockRejectedValue(new Error("API connection refused")),
  };
}

// ---------------------------------------------------------------------------
// Helper: connect MCP client ↔ server via in-memory transport
// ---------------------------------------------------------------------------

async function createConnectedClient(apiClient: RhumbApiClient) {
  const server = createServer(apiClient);
  const [clientTransport, serverTransport] = InMemoryTransport.createLinkedPair();

  const client = new Client({ name: "test-client", version: "1.0.0" });

  await Promise.all([
    client.connect(clientTransport),
    server.connect(serverTransport),
  ]);

  return { client, server };
}

/**
 * Extract the JSON text from a callTool result.
 * callTool returns `{ [x: string]: unknown; content: ... }` — the index
 * signature makes `content` resolve to `unknown` under strict mode.
 * We use the validated result schema to work around this safely.
 */
function extractText(result: Awaited<ReturnType<Client["callTool"]>>): string {
  const content = result.content as Array<{ type: string; text?: string }>;
  const first = content[0];
  if (!first || first.type !== "text" || typeof first.text !== "string") {
    throw new Error("Expected text content in tool result");
  }
  return first.text;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("e2e: MCP server integration", () => {
  describe("tool registration", () => {
    it("lists all 8 registered tools", async () => {
      const apiClient = createMockApiClient();
      const { client } = await createConnectedClient(apiClient);

      const { tools } = await client.listTools();
      const toolNames = tools.map((t) => t.name).sort();

      expect(toolNames).toEqual([
        "discover_capabilities",
        "estimate_capability",
        "execute_capability",
        "find_tools",
        "get_alternatives",
        "get_failure_modes",
        "get_score",
        "resolve_capability",
      ]);
      expect(tools).toHaveLength(8);

      // Each tool has a description and input schema
      for (const tool of tools) {
        expect(tool.description).toBeTruthy();
        expect(tool.inputSchema).toBeDefined();
      }
    });
  });

  describe("find_tools", () => {
    it("returns ranked results with correct output shape", async () => {
      const apiClient = createMockApiClient();
      const { client } = await createConnectedClient(apiClient);

      const result = await client.callTool({
        name: "find_tools",
        arguments: { query: "email delivery", limit: 3 },
      }, CallToolResultSchema);

      const parsed: FindToolOutput = JSON.parse(extractText(result));
      expect(parsed.tools.length).toBeGreaterThan(0);
      expect(parsed.tools.length).toBeLessThanOrEqual(3);

      // Verify ranking — first result should have highest score
      expect(parsed.tools[0].slug).toBe("resend");
      expect(parsed.tools[0].aggregateScore).toBe(91);

      // Verify output shape
      for (const tool of parsed.tools) {
        expect(tool).toHaveProperty("name");
        expect(tool).toHaveProperty("slug");
        expect(tool).toHaveProperty("aggregateScore");
        expect(tool).toHaveProperty("executionScore");
        expect(tool).toHaveProperty("accessScore");
        expect(tool).toHaveProperty("explanation");
      }

      expect(apiClient.searchServices).toHaveBeenCalledWith("email delivery");
    });
  });

  describe("get_score", () => {
    it("returns full breakdown with correct fields", async () => {
      const apiClient = createMockApiClient();
      const { client } = await createConnectedClient(apiClient);

      const result = await client.callTool({
        name: "get_score",
        arguments: { slug: "resend" },
      }, CallToolResultSchema);

      const parsed: GetScoreOutput = JSON.parse(extractText(result));

      expect(parsed.slug).toBe("resend");
      expect(parsed.aggregateScore).toBe(91);
      expect(parsed.executionScore).toBe(93);
      expect(parsed.accessScore).toBe(89);
      expect(parsed.confidence).toBe(0.97);
      expect(parsed.tier).toBe("excellent");
      expect(parsed.explanation).toBeTruthy();
      expect(parsed.freshness).toBeTruthy();
    });
  });

  describe("get_alternatives", () => {
    it("returns peer-ranked alternatives", async () => {
      const apiClient = createMockApiClient();
      const { client } = await createConnectedClient(apiClient);

      // Use sendgrid (score 72) — resend (91) and postmark (85) should appear
      // Override getServiceScore to return sendgrid's score
      (apiClient.getServiceScore as ReturnType<typeof vi.fn>).mockImplementation(
        async (slug: string) => {
          if (slug === "sendgrid")
            return {
              ...mockScore,
              slug: "sendgrid",
              aggregateScore: 72,
              executionScore: 75,
              accessScore: 69,
            };
          return null;
        }
      );

      const result = await client.callTool({
        name: "get_alternatives",
        arguments: { slug: "sendgrid" },
      }, CallToolResultSchema);

      const parsed: GetAlternativesOutput = JSON.parse(extractText(result));

      expect(parsed.alternatives.length).toBeGreaterThan(0);

      // Verify output shape
      for (const alt of parsed.alternatives) {
        expect(alt).toHaveProperty("name");
        expect(alt).toHaveProperty("slug");
        expect(alt).toHaveProperty("aggregateScore");
        expect(alt).toHaveProperty("reason");
      }

      // All alternatives should have higher score than sendgrid (72)
      for (const alt of parsed.alternatives) {
        expect(alt.aggregateScore).toBeGreaterThan(72);
      }
    });
  });

  describe("get_failure_modes", () => {
    it("returns failure patterns with correct structure", async () => {
      const apiClient = createMockApiClient();
      const { client } = await createConnectedClient(apiClient);

      const result = await client.callTool({
        name: "get_failure_modes",
        arguments: { slug: "resend" },
      }, CallToolResultSchema);

      const parsed: GetFailureModesOutput = JSON.parse(extractText(result));

      expect(parsed.failures.length).toBeGreaterThan(0);

      for (const failure of parsed.failures) {
        expect(failure).toHaveProperty("pattern");
        expect(failure).toHaveProperty("impact");
        expect(failure).toHaveProperty("frequency");
        expect(failure).toHaveProperty("workaround");
        expect(typeof failure.pattern).toBe("string");
        expect(typeof failure.impact).toBe("string");
        // Should NOT expose internal tags
        expect(failure).not.toHaveProperty("tags");
      }

      expect(parsed.failures[0].pattern).toBe(
        "SDK timeout on large batch sends"
      );
    });
  });

  describe("error handling and resilience", () => {
    it("handles API errors gracefully without crashing", async () => {
      const apiClient = createErrorApiClient();
      const { client } = await createConnectedClient(apiClient);

      // find_tools — should return empty tools, not throw
      const findResult = await client.callTool({
        name: "find_tools",
        arguments: { query: "email" },
      }, CallToolResultSchema);
      const findParsed: FindToolOutput = JSON.parse(extractText(findResult));
      expect(findParsed.tools).toEqual([]);

      // get_score — should return error response, not throw
      const scoreResult = await client.callTool({
        name: "get_score",
        arguments: { slug: "sendgrid" },
      }, CallToolResultSchema);
      const scoreParsed: GetScoreOutput = JSON.parse(extractText(scoreResult));
      expect(scoreParsed.slug).toBe("sendgrid");
      expect(scoreParsed.tier).toBe("unknown");
      expect(scoreParsed.explanation).toContain("Failed to fetch score");

      // get_alternatives — should return empty alternatives
      const altResult = await client.callTool({
        name: "get_alternatives",
        arguments: { slug: "sendgrid" },
      }, CallToolResultSchema);
      const altParsed: GetAlternativesOutput = JSON.parse(extractText(altResult));
      expect(altParsed.alternatives).toEqual([]);

      // get_failure_modes — should return empty failures
      const failResult = await client.callTool({
        name: "get_failure_modes",
        arguments: { slug: "sendgrid" },
      }, CallToolResultSchema);
      const failParsed: GetFailureModesOutput = JSON.parse(extractText(failResult));
      expect(failParsed.failures).toEqual([]);
    });

    it("handles missing/not-found service gracefully", async () => {
      const apiClient = createMockApiClient();
      const { client } = await createConnectedClient(apiClient);

      // get_score with nonexistent slug
      const scoreResult = await client.callTool({
        name: "get_score",
        arguments: { slug: "nonexistent" },
      }, CallToolResultSchema);
      const scoreParsed: GetScoreOutput = JSON.parse(extractText(scoreResult));
      expect(scoreParsed.slug).toBe("nonexistent");
      expect(scoreParsed.aggregateScore).toBeNull();
      expect(scoreParsed.tier).toBe("unknown");
      expect(scoreParsed.explanation).toContain("not found");

      // get_failure_modes with nonexistent slug
      const failResult = await client.callTool({
        name: "get_failure_modes",
        arguments: { slug: "nonexistent" },
      }, CallToolResultSchema);
      const failParsed: GetFailureModesOutput = JSON.parse(extractText(failResult));
      expect(failParsed.failures).toEqual([]);
    });
  });
});

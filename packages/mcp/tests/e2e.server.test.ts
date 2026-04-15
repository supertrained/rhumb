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
import type {
  FindServiceOutput,
  GetScoreOutput,
  GetAlternativesOutput,
  GetFailureModesOutput,
  EstimateCapabilityOutput,
  ResolveCapabilityOutput,
  ListRecipesOutput,
  GetRecipeOutput,
  RecipeExecuteOutput,
} from "../src/types.js";

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
          recommendationReason: "High AN score (91), 100 free calls/month",
          credentialModes: ["byok"],
          configured: false,
          availableForExecute: false,
          circuitState: "open"
        }
      ],
      fallbackChain: ["resend", "sendgrid"],
      relatedBundles: [],
      executeHint: {
        preferredProvider: "sendgrid",
        selectionReason: "higher_ranked_provider_unavailable",
        skippedProviderSlugs: ["resend"],
        unavailableProviderSlugs: ["resend"],
        notExecuteReadyProviderSlugs: [],
        endpointPattern: "POST /v3/mail/send",
        estimatedCostUsd: 0.001,
        authMethod: "api_key",
        credentialModes: ["byok"],
        configured: true,
        credentialModesUrl: "/v1/capabilities/email.send/credential-modes",
        preferredCredentialMode: "byok",
        fallbackProviders: [],
        setupHint: null,
        setupUrl: null
      },
      recoveryHint: null
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
      credentialMode: "byok",
      costEstimateUsd: null,
      circuitState: "closed",
      endpointPattern: "POST /emails",
      executeReadiness: {
        status: "auth_required",
        message: "Add X-Rhumb-Key before execute.",
        resolveUrl: "/v1/capabilities/email.send/resolve",
        credentialModesUrl: "/v1/capabilities/email.send/credential-modes",
        authHandoff: {
          reason: "auth_required",
          recommendedPath: "governed_api_key",
          retryUrl: "/v1/capabilities/email.send/execute",
          docsUrl: "/docs#resolve-mental-model",
          paths: [
            {
              kind: "governed_api_key",
              recommended: true,
              setupUrl: "/auth/login",
              retryHeader: "X-Rhumb-Key",
              summary: "Default for most buyers and most repeat agent traffic.",
              requiresHumanSetup: true,
              automaticAfterSetup: true,
              requiresWalletSupport: null,
            },
          ],
        },
      },
    }),
    listRecipes: vi.fn().mockResolvedValue({
      items: [
        {
          recipeId: "transcribe_and_notify",
          name: "Transcribe and notify",
          version: "1.0.0",
          category: "productivity",
          stability: "beta",
          tier: "premium",
          stepCount: 2,
          maxTotalCostUsd: 0.5,
        }
      ],
      total: 1,
      limit: 20,
      offset: 0,
    }),
    getRecipe: vi.fn().mockResolvedValue({
      recipeId: "transcribe_and_notify",
      name: "Transcribe and notify",
      version: "1.0.0",
      category: "productivity",
      stability: "beta",
      tier: "premium",
      stepCount: 2,
      maxTotalCostUsd: 0.5,
      definition: { recipe_id: "transcribe_and_notify", steps: [{ step_id: "transcribe" }, { step_id: "notify" }] },
      inputsSchema: { type: "object", required: ["audio_url", "to"] },
      outputsSchema: { type: "object" },
      layer: 3,
    }),
    executeRecipe: vi.fn().mockResolvedValue({
      executionId: "rexec_123",
      recipeId: "transcribe_and_notify",
      status: "completed",
      totalCostUsd: 0.04,
      totalDurationMs: 210,
      startedAt: "2026-03-31T12:00:00Z",
      completedAt: "2026-03-31T12:00:01Z",
      error: null,
      receiptChainHash: "hash123",
      deduplicated: false,
      layer: 3,
      outputs: { notify: { message_id: "msg_123" } },
      stepResults: [
        {
          stepId: "transcribe",
          capabilityId: "media.transcribe",
          status: "succeeded",
          outputs: { transcript_text: "hello world" },
          costUsd: 0.03,
          durationMs: 120,
          receiptId: "rcpt_step_1",
          error: null,
          retriesUsed: 0,
          providerUsed: "assemblyai",
        },
        {
          stepId: "notify",
          capabilityId: "email.send",
          status: "succeeded",
          outputs: { message_id: "msg_123" },
          costUsd: 0.01,
          durationMs: 90,
          receiptId: "rcpt_step_2",
          error: null,
          retriesUsed: 0,
          providerUsed: "resend",
        }
      ],
    }),
    listCeremonies: vi.fn().mockResolvedValue([]),
    getCeremony: vi.fn().mockResolvedValue(null),
    listManagedCapabilities: vi.fn().mockResolvedValue([]),
    getBudget: vi.fn().mockResolvedValue({ unlimited: true }),
    setBudget: vi.fn().mockResolvedValue({}),
    getSpend: vi.fn().mockResolvedValue({ total_spend_usd: 0, total_executions: 0, by_capability: [], by_provider: [] }),
    getRoutingStrategy: vi.fn().mockResolvedValue({ strategy: "balanced", quality_floor: 6.0 }),
    setRoutingStrategy: vi.fn().mockResolvedValue({}),
    getUsageTelemetry: vi.fn().mockResolvedValue({ agent_id: "agent_test", period_days: 7, summary: { total_calls: 3, successful_calls: 3, failed_calls: 0, total_cost_usd: 0.12, avg_latency_ms: 140, p50_latency_ms: 142, p95_latency_ms: 142 }, by_capability: [], by_provider: [], by_time: [] }),
    getBalance: vi.fn().mockResolvedValue({ balance_usd: 25, balance_usd_cents: 2500, auto_reload_enabled: false }),
    createCheckout: vi.fn().mockResolvedValue({ checkout_url: 'https://checkout.stripe.com/test', session_id: 'cs_test' }),
    getLedger: vi.fn().mockResolvedValue({ entries: [], total_count: 0 }),
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
    listRecipes: vi
      .fn()
      .mockRejectedValue(new Error("API connection refused")),
    getRecipe: vi
      .fn()
      .mockRejectedValue(new Error("API connection refused")),
    executeRecipe: vi
      .fn()
      .mockRejectedValue(new Error("API connection refused")),
    listCeremonies: vi.fn().mockResolvedValue([]),
    getCeremony: vi.fn().mockResolvedValue(null),
    listManagedCapabilities: vi.fn().mockResolvedValue([]),
    getBudget: vi.fn().mockResolvedValue({ unlimited: true }),
    setBudget: vi.fn().mockResolvedValue({}),
    getSpend: vi.fn().mockResolvedValue({ total_spend_usd: 0, total_executions: 0, by_capability: [], by_provider: [] }),
    getRoutingStrategy: vi.fn().mockResolvedValue({ strategy: "balanced", quality_floor: 6.0 }),
    setRoutingStrategy: vi.fn().mockResolvedValue({}),
    getUsageTelemetry: vi.fn().mockRejectedValue(new Error("API connection refused")),
    getBalance: vi.fn().mockResolvedValue({ balance_usd: 25, balance_usd_cents: 2500, auto_reload_enabled: false }),
    createCheckout: vi.fn().mockResolvedValue({ checkout_url: 'https://checkout.stripe.com/test', session_id: 'cs_test' }),
    getLedger: vi.fn().mockResolvedValue({ entries: [], total_count: 0 }),
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
    it("lists all 21 registered tools", async () => {
      const apiClient = createMockApiClient();
      const { client } = await createConnectedClient(apiClient);

      const { tools } = await client.listTools();
      const toolNames = tools.map((t) => t.name).sort();

      expect(toolNames).toEqual([
        "budget",
        "check_balance",
        "check_credentials",
        "credential_ceremony",
        "discover_capabilities",
        "estimate_capability",
        "execute_capability",
        "find_services",
        "get_alternatives",
        "get_failure_modes",
        "get_ledger",
        "get_payment_url",
        "get_receipt",
        "get_score",
        "resolve_capability",
        "rhumb_get_recipe",
        "rhumb_list_recipes",
        "rhumb_recipe_execute",
        "routing",
        "spend",
        "usage_telemetry",
      ]);
      expect(tools).toHaveLength(21);

      // Each tool has a description and input schema
      for (const tool of tools) {
        expect(tool.description).toBeTruthy();
        expect(tool.inputSchema).toBeDefined();
      }

      const checkCredentialsTool = tools.find((tool) => tool.name === "check_credentials");
      expect(checkCredentialsTool?.description).toContain("direct bundles");
      expect(checkCredentialsTool?.description).toContain("specific path");
      expect(checkCredentialsTool?.inputSchema).toMatchObject({
        type: "object",
        properties: expect.objectContaining({
          capability: expect.any(Object),
        }),
      });
    });
  });

  describe("find_services", () => {
    it("returns ranked results with correct output shape", async () => {
      const apiClient = createMockApiClient();
      const { client } = await createConnectedClient(apiClient);

      const result = await client.callTool({
        name: "find_services",
        arguments: { query: "email delivery", limit: 3 },
      }, CallToolResultSchema);

      const parsed: FindServiceOutput = JSON.parse(extractText(result));
      expect(parsed.services.length).toBeGreaterThan(0);
      expect(parsed.services.length).toBeLessThanOrEqual(3);

      // Verify ranking — first result should have highest score
      expect(parsed.services[0].slug).toBe("resend");
      expect(parsed.services[0].aggregateScore).toBe(91);

      // Verify output shape
      for (const service of parsed.services) {
        expect(service).toHaveProperty("name");
        expect(service).toHaveProperty("slug");
        expect(service).toHaveProperty("aggregateScore");
        expect(service).toHaveProperty("executionScore");
        expect(service).toHaveProperty("accessScore");
        expect(service).toHaveProperty("explanation");
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

  describe("resolve_capability", () => {
    it("returns execute hint and degraded-provider context", async () => {
      const apiClient = createMockApiClient();
      const { client } = await createConnectedClient(apiClient);

      const result = await client.callTool({
        name: "resolve_capability",
        arguments: { capability: "email.send" },
      }, CallToolResultSchema);

      const parsed: ResolveCapabilityOutput = JSON.parse(extractText(result));

      expect(parsed.capability).toBe("email.send");
      expect(parsed.providers[0].availableForExecute).toBe(false);
      expect(parsed.executeHint?.preferredProvider).toBe("sendgrid");
      expect(parsed.executeHint?.selectionReason).toBe("higher_ranked_provider_unavailable");
      expect(parsed.executeHint?.unavailableProviderSlugs).toEqual(["resend"]);
      expect(parsed.recoveryHint).toBeNull();
    });

    it("forwards credential_mode filters through the MCP tool", async () => {
      const apiClient = createMockApiClient();
      const { client } = await createConnectedClient(apiClient);

      await client.callTool({
        name: "resolve_capability",
        arguments: { capability: "email.send", credential_mode: "agent_vault" },
      }, CallToolResultSchema);

      expect(apiClient.resolveCapability).toHaveBeenCalledWith(
        "email.send",
        expect.objectContaining({ credentialMode: "agent_vault" })
      );
    });

    it("returns recovery rerun and handoff fields when resolve dead-ends", async () => {
      const apiClient = createMockApiClient();
      vi.mocked(apiClient.resolveCapability).mockResolvedValueOnce({
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
            recommendationReason: "High AN score (91), 100 free calls/month",
            credentialModes: ["byok"],
            configured: false,
            availableForExecute: false,
            circuitState: "closed"
          }
        ],
        fallbackChain: [],
        relatedBundles: [],
        executeHint: null,
        recoveryHint: {
          reason: "no_execute_ready_providers",
          requestedCredentialMode: "byok",
          resolveUrl: "/v1/capabilities/email.send/resolve",
          credentialModesUrl: "/v1/capabilities/email.send/credential-modes",
          supportedProviderSlugs: ["resend"],
          supportedCredentialModes: ["byok"],
          unavailableProviderSlugs: [],
          notExecuteReadyProviderSlugs: ["resend"],
          alternateExecuteHint: null,
          setupHandoff: {
            preferredProvider: "resend",
            selectionReason: "highest_ranked_provider",
            endpointPattern: null,
            authMethod: "api_key",
            credentialModes: ["byok"],
            configured: false,
            credentialModesUrl: "/v1/capabilities/email.send/credential-modes",
            preferredCredentialMode: "byok",
            fallbackProviders: [],
            setupHint: "Set RHUMB_CREDENTIAL_RESEND_API_KEY environment variable or configure via proxy credentials",
            setupUrl: "/v1/services/resend/ceremony"
          }
        }
      });

      const { client } = await createConnectedClient(apiClient);

      const result = await client.callTool({
        name: "resolve_capability",
        arguments: { capability: "email.send" },
      }, CallToolResultSchema);

      const parsed: ResolveCapabilityOutput = JSON.parse(extractText(result));

      expect(parsed.executeHint).toBeNull();
      expect(parsed.recoveryHint?.resolveUrl).toBe("/v1/capabilities/email.send/resolve");
      expect(parsed.recoveryHint?.setupHandoff?.setupUrl).toBe("/v1/services/resend/ceremony");
      expect(parsed.recoveryHint?.alternateExecuteHint).toBeNull();
    });
  });

  describe("estimate_capability", () => {
    it("returns execute readiness handoffs when estimate is auth-blocked", async () => {
      const apiClient = createMockApiClient();
      const { client } = await createConnectedClient(apiClient);

      const result = await client.callTool({
        name: "estimate_capability",
        arguments: { capability_id: "email.send" },
      }, CallToolResultSchema);

      const parsed: EstimateCapabilityOutput = JSON.parse(extractText(result));

      expect(parsed.credentialMode).toBe("byok");
      expect(parsed.executeReadiness?.status).toBe("auth_required");
      expect(parsed.executeReadiness?.resolveUrl).toBe("/v1/capabilities/email.send/resolve");
      expect(parsed.executeReadiness?.authHandoff?.paths[0]?.retryHeader).toBe("X-Rhumb-Key");
    });
  });

  describe("recipe tools", () => {
    it("lists published recipes", async () => {
      const apiClient = createMockApiClient();
      const { client } = await createConnectedClient(apiClient);

      const result = await client.callTool({
        name: "rhumb_list_recipes",
        arguments: { category: "productivity", limit: 10 },
      }, CallToolResultSchema);

      const parsed: ListRecipesOutput = JSON.parse(extractText(result));
      expect(parsed.total).toBe(1);
      expect(parsed.recipes[0].recipeId).toBe("transcribe_and_notify");
    });

    it("gets a recipe definition", async () => {
      const apiClient = createMockApiClient();
      const { client } = await createConnectedClient(apiClient);

      const result = await client.callTool({
        name: "rhumb_get_recipe",
        arguments: { recipe_id: "transcribe_and_notify" },
      }, CallToolResultSchema);

      const parsed: GetRecipeOutput = JSON.parse(extractText(result));
      expect(parsed.recipeId).toBe("transcribe_and_notify");
      expect((parsed.definition.steps as unknown[]).length).toBe(2);
      expect(parsed.layer).toBe(3);
    });

    it("executes a published recipe", async () => {
      const apiClient = createMockApiClient();
      const { client } = await createConnectedClient(apiClient);

      const result = await client.callTool({
        name: "rhumb_recipe_execute",
        arguments: {
          recipe_id: "transcribe_and_notify",
          inputs: { audio_url: "https://example.com/audio.mp3", to: "tom@example.com" },
          credential_mode: "byo",
        },
      }, CallToolResultSchema);

      const parsed: RecipeExecuteOutput = JSON.parse(extractText(result));
      expect(parsed.recipeId).toBe("transcribe_and_notify");
      expect(parsed.status).toBe("completed");
      expect(parsed.stepResults).toHaveLength(2);
      expect(parsed.outputs.notify).toBeDefined();
    });
  });

  describe("error handling and resilience", () => {
    it("handles API errors gracefully without crashing", async () => {
      const apiClient = createErrorApiClient();
      const { client } = await createConnectedClient(apiClient);

      // find_services — should return empty services, not throw
      const findResult = await client.callTool({
        name: "find_services",
        arguments: { query: "email" },
      }, CallToolResultSchema);
      const findParsed: FindServiceOutput = JSON.parse(extractText(findResult));
      expect(findParsed.services).toEqual([]);

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

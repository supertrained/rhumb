/**
 * Tests for discover_capabilities and resolve_capability tool handlers
 */

import { describe, it, expect, vi } from "vitest";
import { handleDiscoverCapabilities } from "../../src/tools/capabilities.js";
import { handleResolveCapability } from "../../src/tools/resolve.js";
import type { RhumbApiClient } from "../../src/api-client.js";

// -- Fixtures -------------------------------------------------------------

const mockCapabilities = [
  {
    id: "email.send",
    domain: "email",
    action: "send",
    description: "Send transactional or marketing email",
    inputHint: "recipient, subject, body",
    outcome: "Email delivered to recipient inbox",
    providerCount: 8,
    topProvider: { slug: "resend", anScore: 7.79, tierLabel: "Native" }
  },
  {
    id: "email.verify",
    domain: "email",
    action: "verify",
    description: "Verify an email address is valid",
    inputHint: "email_address",
    outcome: "Verification result",
    providerCount: 0,
    topProvider: null
  }
];

const mockResolveResult = {
  capability: "email.send",
  providers: [
    {
      serviceSlug: "resend",
      serviceName: "Resend",
      anScore: 7.79,
      costPerCall: null,
      freeTierCalls: 100,
      authMethod: "api_key",
      endpointPattern: "POST /emails",
      recommendation: "preferred",
      recommendationReason: "High AN score (7.8), 100 free calls/month",
      credentialModes: ["byok"],
      configured: false,
      availableForExecute: false,
      circuitState: "open"
    },
    {
      serviceSlug: "sendgrid",
      serviceName: "SendGrid",
      anScore: 6.35,
      costPerCall: 0.001,
      freeTierCalls: 100,
      authMethod: "api_key",
      endpointPattern: "POST /v3/mail/send",
      recommendation: "available",
      recommendationReason: "Solid AN score (6.4), $0.001/call (100 free)",
      credentialModes: ["byok"],
      configured: true,
      availableForExecute: true,
      circuitState: "closed"
    }
  ],
  fallbackChain: ["resend", "sendgrid", "amazon-ses"],
  relatedBundles: ["email.compose_and_deliver"],
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
    fallbackProviders: ["amazon-ses"],
    setupHint: null,
    setupUrl: null
  },
  recoveryHint: null
};

function createMockClient(overrides: Partial<RhumbApiClient> = {}): RhumbApiClient {
  return {
    searchServices: vi.fn().mockResolvedValue([]),
    getServiceScore: vi.fn().mockResolvedValue(null),
    discoverCapabilities: vi.fn().mockResolvedValue({ items: mockCapabilities, total: 2 }),
    resolveCapability: vi.fn().mockResolvedValue(mockResolveResult),
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
    getUsageTelemetry: vi.fn().mockResolvedValue({ agent_id: "", period_days: 7, summary: { total_calls: 0, successful_calls: 0, failed_calls: 0, total_cost_usd: 0, avg_latency_ms: 0, p50_latency_ms: 0, p95_latency_ms: 0 }, by_capability: [], by_provider: [], by_time: [] }),
    getBalance: vi.fn().mockResolvedValue({ balance_usd: 25, balance_usd_cents: 2500, auto_reload_enabled: false }),
    createCheckout: vi.fn().mockResolvedValue({ checkout_url: 'https://checkout.stripe.com/test', session_id: 'cs_test' }),
    getLedger: vi.fn().mockResolvedValue({ entries: [], total_count: 0 }),
    ...overrides
  };
}

// -- discover_capabilities tests -----------------------------------------

describe("discover_capabilities", () => {
  it("returns capabilities with provider counts", async () => {
    const client = createMockClient();
    const result = await handleDiscoverCapabilities({}, client);

    expect(result.capabilities).toHaveLength(2);
    expect(result.total).toBe(2);
    expect(result.capabilities[0].id).toBe("email.send");
    expect(result.capabilities[0].providerCount).toBe(8);
  });

  it("passes domain filter to API", async () => {
    const client = createMockClient();
    await handleDiscoverCapabilities({ domain: "email" }, client);

    expect(client.discoverCapabilities).toHaveBeenCalledWith(
      expect.objectContaining({ domain: "email" })
    );
  });

  it("passes search query to API", async () => {
    const client = createMockClient();
    await handleDiscoverCapabilities({ search: "send" }, client);

    expect(client.discoverCapabilities).toHaveBeenCalledWith(
      expect.objectContaining({ search: "send" })
    );
  });

  it("applies default limit of 20", async () => {
    const client = createMockClient();
    await handleDiscoverCapabilities({}, client);

    expect(client.discoverCapabilities).toHaveBeenCalledWith(
      expect.objectContaining({ limit: 20 })
    );
  });

  it("returns empty list on API error", async () => {
    const client = createMockClient({
      discoverCapabilities: vi.fn().mockRejectedValue(new Error("API down"))
    });
    const result = await handleDiscoverCapabilities({}, client);

    expect(result.capabilities).toHaveLength(0);
    expect(result.total).toBe(0);
  });

  it("includes top provider when available", async () => {
    const client = createMockClient();
    const result = await handleDiscoverCapabilities({}, client);

    expect(result.capabilities[0].topProvider).not.toBeNull();
    expect(result.capabilities[0].topProvider!.slug).toBe("resend");
    expect(result.capabilities[0].topProvider!.anScore).toBe(7.79);
  });

  it("handles capabilities with no providers", async () => {
    const client = createMockClient();
    const result = await handleDiscoverCapabilities({}, client);

    const noProvider = result.capabilities.find(c => c.id === "email.verify");
    expect(noProvider).toBeDefined();
    expect(noProvider!.providerCount).toBe(0);
    expect(noProvider!.topProvider).toBeNull();
  });
});

// -- resolve_capability tests --------------------------------------------

describe("resolve_capability", () => {
  it("returns ranked providers for a capability", async () => {
    const client = createMockClient();
    const result = await handleResolveCapability({ capability: "email.send" }, client);

    expect(result.capability).toBe("email.send");
    expect(result.providers).toHaveLength(2);
    expect(result.providers[0].serviceSlug).toBe("resend");
    expect(result.providers[0].recommendation).toBe("preferred");
  });

  it("includes fallback chain", async () => {
    const client = createMockClient();
    const result = await handleResolveCapability({ capability: "email.send" }, client);

    expect(result.fallbackChain).toEqual(["resend", "sendgrid", "amazon-ses"]);
  });

  it("includes related bundles", async () => {
    const client = createMockClient();
    const result = await handleResolveCapability({ capability: "email.send" }, client);

    expect(result.relatedBundles).toContain("email.compose_and_deliver");
  });

  it("includes execute hint machine-readable handoff fields", async () => {
    const client = createMockClient();
    const result = await handleResolveCapability({ capability: "email.send" }, client);

    expect(result.executeHint?.preferredProvider).toBe("sendgrid");
    expect(result.executeHint?.selectionReason).toBe("higher_ranked_provider_unavailable");
    expect(result.executeHint?.unavailableProviderSlugs).toEqual(["resend"]);
    expect(result.executeHint?.fallbackProviders).toEqual(["amazon-ses"]);
  });

  it("includes recovery hint when resolve has no execute-ready providers", async () => {
    const client = createMockClient({
      resolveCapability: vi.fn().mockResolvedValue({
        ...mockResolveResult,
        fallbackChain: [],
        executeHint: null,
        recoveryHint: {
          reason: "no_execute_ready_providers",
          requestedCredentialMode: "byok",
          resolveUrl: "/v1/capabilities/email.send/resolve",
          credentialModesUrl: "/v1/capabilities/email.send/credential-modes",
          supportedProviderSlugs: ["resend", "sendgrid"],
          supportedCredentialModes: ["byok", "agent_vault"],
          unavailableProviderSlugs: ["resend"],
          notExecuteReadyProviderSlugs: ["sendgrid"],
          alternateExecuteHint: {
            preferredProvider: "sendgrid",
            selectionReason: "higher_ranked_provider_unavailable",
            endpointPattern: "POST /v3/mail/send",
            authMethod: "api_key",
            credentialModes: ["byok"],
            configured: true,
            credentialModesUrl: "/v1/capabilities/email.send/credential-modes",
            preferredCredentialMode: "byok",
            fallbackProviders: ["amazon-ses"],
            setupHint: null,
            setupUrl: null
          },
          setupHandoff: null
        }
      })
    });
    const result = await handleResolveCapability({ capability: "email.send" }, client);

    expect(result.executeHint).toBeNull();
    expect(result.recoveryHint?.reason).toBe("no_execute_ready_providers");
    expect(result.recoveryHint?.resolveUrl).toBe("/v1/capabilities/email.send/resolve");
    expect(result.recoveryHint?.unavailableProviderSlugs).toEqual(["resend"]);
    expect(result.recoveryHint?.notExecuteReadyProviderSlugs).toEqual(["sendgrid"]);
    expect(result.recoveryHint?.alternateExecuteHint?.endpointPattern).toBe("POST /v3/mail/send");
    expect(result.recoveryHint?.setupHandoff).toBeNull();
  });

  it("includes setup handoff when recovery points at setup instead of execute", async () => {
    const client = createMockClient({
      resolveCapability: vi.fn().mockResolvedValue({
        ...mockResolveResult,
        fallbackChain: [],
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
      })
    });

    const result = await handleResolveCapability({ capability: "email.send" }, client);

    expect(result.recoveryHint?.alternateExecuteHint).toBeNull();
    expect(result.recoveryHint?.setupHandoff?.preferredProvider).toBe("resend");
    expect(result.recoveryHint?.setupHandoff?.setupUrl).toBe("/v1/services/resend/ceremony");
  });

  it("returns empty providers when capability not found", async () => {
    const client = createMockClient({
      resolveCapability: vi.fn().mockResolvedValue(null)
    });
    const result = await handleResolveCapability({ capability: "nonexistent.action" }, client);

    expect(result.capability).toBe("nonexistent.action");
    expect(result.providers).toHaveLength(0);
    expect(result.fallbackChain).toHaveLength(0);
    expect(result.executeHint).toBeNull();
    expect(result.recoveryHint).toBeNull();
  });

  it("returns empty providers on API error", async () => {
    const client = createMockClient({
      resolveCapability: vi.fn().mockRejectedValue(new Error("API down"))
    });
    const result = await handleResolveCapability({ capability: "email.send" }, client);

    expect(result.providers).toHaveLength(0);
    expect(result.executeHint).toBeNull();
    expect(result.recoveryHint).toBeNull();
  });

  it("includes cost and auth info per provider", async () => {
    const client = createMockClient();
    const result = await handleResolveCapability({ capability: "email.send" }, client);

    const sg = result.providers.find(p => p.serviceSlug === "sendgrid");
    expect(sg).toBeDefined();
    expect(sg!.costPerCall).toBe(0.001);
    expect(sg!.authMethod).toBe("api_key");
    expect(sg!.endpointPattern).toBe("POST /v3/mail/send");
  });

  it("includes recommendation reason", async () => {
    const client = createMockClient();
    const result = await handleResolveCapability({ capability: "email.send" }, client);

    expect(result.providers[0].recommendationReason).toContain("AN score");
  });
});

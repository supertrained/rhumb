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
      recommendationReason: "High AN score (7.8), 100 free calls/month"
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
      recommendationReason: "Solid AN score (6.4), $0.001/call (100 free)"
    }
  ],
  fallbackChain: ["resend", "sendgrid", "amazon-ses"],
  relatedBundles: ["email.compose_and_deliver"]
};

function createMockClient(overrides: Partial<RhumbApiClient> = {}): RhumbApiClient {
  return {
    searchServices: vi.fn().mockResolvedValue([]),
    getServiceScore: vi.fn().mockResolvedValue(null),
    discoverCapabilities: vi.fn().mockResolvedValue({ items: mockCapabilities, total: 2 }),
    resolveCapability: vi.fn().mockResolvedValue(mockResolveResult),
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

  it("returns empty providers when capability not found", async () => {
    const client = createMockClient({
      resolveCapability: vi.fn().mockResolvedValue(null)
    });
    const result = await handleResolveCapability({ capability: "nonexistent.action" }, client);

    expect(result.capability).toBe("nonexistent.action");
    expect(result.providers).toHaveLength(0);
    expect(result.fallbackChain).toHaveLength(0);
  });

  it("returns empty providers on API error", async () => {
    const client = createMockClient({
      resolveCapability: vi.fn().mockRejectedValue(new Error("API down"))
    });
    const result = await handleResolveCapability({ capability: "email.send" }, client);

    expect(result.providers).toHaveLength(0);
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

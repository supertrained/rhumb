/**
 * Tests for execute_capability and estimate_capability tool handlers
 */

import { describe, it, expect, vi } from "vitest";
import type { RhumbApiClient } from "../../src/api-client.js";
import { handleExecuteCapability } from "../../src/tools/execute.js";
import { handleEstimateCapability } from "../../src/tools/estimate.js";

const mockExecuteResult = {
  capabilityId: "email.send",
  providerUsed: "resend",
  credentialMode: "byo",
  upstreamStatus: 200,
  upstreamResponse: { id: "msg_abc123" },
  costEstimateUsd: null,
  latencyMs: 142.3,
  fallbackAttempted: false,
  fallbackProvider: null,
  executionId: "exec_01JPPX"
};

const mockEstimateResult = {
  capabilityId: "email.send",
  provider: "resend",
  credentialMode: "byo",
  costEstimateUsd: null,
  circuitState: "closed",
  endpointPattern: "POST /emails"
};

function createMockClient(overrides: Partial<RhumbApiClient> = {}): RhumbApiClient {
  return {
    searchServices: vi.fn().mockResolvedValue([]),
    getServiceScore: vi.fn().mockResolvedValue(null),
    discoverCapabilities: vi.fn().mockResolvedValue({ items: [], total: 0 }),
    resolveCapability: vi.fn().mockResolvedValue(null),
    executeCapability: vi.fn().mockResolvedValue(mockExecuteResult),
    estimateCapability: vi.fn().mockResolvedValue(mockEstimateResult),
    listCeremonies: vi.fn().mockResolvedValue([]),
    getCeremony: vi.fn().mockResolvedValue(null),
    listManagedCapabilities: vi.fn().mockResolvedValue([]),
    getBudget: vi.fn().mockResolvedValue({ unlimited: true }),
    setBudget: vi.fn().mockResolvedValue({}),
    getSpend: vi.fn().mockResolvedValue({ total_spend_usd: 0, total_executions: 0, by_capability: [], by_provider: [] }),
    getRoutingStrategy: vi.fn().mockResolvedValue({ strategy: "balanced", quality_floor: 6.0 }),
    setRoutingStrategy: vi.fn().mockResolvedValue({}),
    ...overrides
  };
}

// -- execute_capability tests --------------------------------------------

describe("execute_capability", () => {
  it("executes a capability and returns result", async () => {
    const client = createMockClient();
    const result = await handleExecuteCapability(
      {
        capability_id: "email.send",
        method: "POST",
        path: "/emails",
        body: { to: "user@example.com", subject: "Hello" }
      },
      client
    );

    expect(result.capabilityId).toBe("email.send");
    expect(result.providerUsed).toBe("resend");
    expect(result.upstreamStatus).toBe(200);
    expect(result.executionId).toBe("exec_01JPPX");
    expect(client.executeCapability).toHaveBeenCalledWith("email.send", {
      provider: undefined,
      method: "POST",
      path: "/emails",
      body: { to: "user@example.com", subject: "Hello" },
      params: undefined,
      credentialMode: undefined,
      idempotencyKey: undefined
    });
  });

  it("passes explicit provider to API", async () => {
    const client = createMockClient();
    await handleExecuteCapability(
      {
        capability_id: "email.send",
        provider: "sendgrid",
        method: "POST",
        path: "/v3/mail/send",
        body: {}
      },
      client
    );

    expect(client.executeCapability).toHaveBeenCalledWith("email.send", expect.objectContaining({
      provider: "sendgrid"
    }));
  });

  it("passes idempotency key to API", async () => {
    const client = createMockClient();
    await handleExecuteCapability(
      {
        capability_id: "email.send",
        method: "POST",
        path: "/emails",
        idempotency_key: "test-uuid-123"
      },
      client
    );

    expect(client.executeCapability).toHaveBeenCalledWith("email.send", expect.objectContaining({
      idempotencyKey: "test-uuid-123"
    }));
  });

  it("passes credential mode to API", async () => {
    const client = createMockClient();
    await handleExecuteCapability(
      {
        capability_id: "email.send",
        method: "POST",
        path: "/emails",
        credential_mode: "rhumb_managed"
      },
      client
    );

    expect(client.executeCapability).toHaveBeenCalledWith("email.send", expect.objectContaining({
      credentialMode: "rhumb_managed"
    }));
  });

  it("returns fallback info when fallback attempted", async () => {
    const client = createMockClient({
      executeCapability: vi.fn().mockResolvedValue({
        ...mockExecuteResult,
        fallbackAttempted: true,
        fallbackProvider: "sendgrid"
      })
    });

    const result = await handleExecuteCapability(
      { capability_id: "email.send", method: "POST", path: "/emails" },
      client
    );

    expect(result.fallbackAttempted).toBe(true);
    expect(result.fallbackProvider).toBe("sendgrid");
  });

  it("returns deduplicated flag for idempotent replays", async () => {
    const client = createMockClient({
      executeCapability: vi.fn().mockResolvedValue({
        ...mockExecuteResult,
        deduplicated: true
      })
    });

    const result = await handleExecuteCapability(
      { capability_id: "email.send", method: "POST", path: "/emails", idempotency_key: "dup" },
      client
    );

    expect(result.deduplicated).toBe(true);
  });

  it("propagates API errors", async () => {
    const client = createMockClient({
      executeCapability: vi.fn().mockRejectedValue(new Error("Execute failed (503): No healthy providers"))
    });

    await expect(
      handleExecuteCapability(
        { capability_id: "email.send", method: "POST", path: "/emails" },
        client
      )
    ).rejects.toThrow("Execute failed (503)");
  });
});

// -- estimate_capability tests -------------------------------------------

describe("estimate_capability", () => {
  it("returns cost estimate without executing", async () => {
    const client = createMockClient();
    const result = await handleEstimateCapability(
      { capability_id: "email.send" },
      client
    );

    expect(result.capabilityId).toBe("email.send");
    expect(result.provider).toBe("resend");
    expect(result.circuitState).toBe("closed");
    expect(result.endpointPattern).toBe("POST /emails");
    expect(client.estimateCapability).toHaveBeenCalledWith("email.send", {
      provider: undefined,
      credentialMode: undefined
    });
  });

  it("passes provider filter to API", async () => {
    const client = createMockClient();
    await handleEstimateCapability(
      { capability_id: "email.send", provider: "sendgrid" },
      client
    );

    expect(client.estimateCapability).toHaveBeenCalledWith("email.send", expect.objectContaining({
      provider: "sendgrid"
    }));
  });

  it("returns cost when available", async () => {
    const client = createMockClient({
      estimateCapability: vi.fn().mockResolvedValue({
    listCeremonies: vi.fn().mockResolvedValue([]),
    getCeremony: vi.fn().mockResolvedValue(null),
    listManagedCapabilities: vi.fn().mockResolvedValue([]),
    getBudget: vi.fn().mockResolvedValue({ unlimited: true }),
    setBudget: vi.fn().mockResolvedValue({}),
    getSpend: vi.fn().mockResolvedValue({ total_spend_usd: 0, total_executions: 0, by_capability: [], by_provider: [] }),
    getRoutingStrategy: vi.fn().mockResolvedValue({ strategy: "balanced", quality_floor: 6.0 }),
    setRoutingStrategy: vi.fn().mockResolvedValue({}),
        ...mockEstimateResult,
        costEstimateUsd: 0.001
      })
    });

    const result = await handleEstimateCapability(
      { capability_id: "email.send" },
      client
    );

    expect(result.costEstimateUsd).toBe(0.001);
  });

  it("shows open circuit state", async () => {
    const client = createMockClient({
      estimateCapability: vi.fn().mockResolvedValue({
        ...mockEstimateResult,
        circuitState: "open"
      })
    });

    const result = await handleEstimateCapability(
      { capability_id: "email.send" },
      client
    );

    expect(result.circuitState).toBe("open");
  });

  it("propagates API errors", async () => {
    const client = createMockClient({
      estimateCapability: vi.fn().mockRejectedValue(new Error("Estimate failed (404)"))
    });

    await expect(
      handleEstimateCapability({ capability_id: "nonexistent.action" }, client)
    ).rejects.toThrow("Estimate failed (404)");
  });
});

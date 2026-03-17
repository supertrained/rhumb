import { describe, it, expect, vi } from "vitest";
import { handleCheckBalance } from "../../src/tools/check-balance.js";
import { handleGetPaymentUrl } from "../../src/tools/get-payment-url.js";
import { handleGetLedger } from "../../src/tools/get-ledger.js";
import type { RhumbApiClient, BalanceResult, CheckoutResult, LedgerResult } from "../../src/api-client.js";

// ---------------------------------------------------------------------------
// Mock client factory
// ---------------------------------------------------------------------------

function createMockClient(overrides?: {
  balance?: BalanceResult;
  checkout?: CheckoutResult;
  ledger?: LedgerResult;
}): RhumbApiClient {
  return {
    searchServices: vi.fn().mockResolvedValue([]),
    getServiceScore: vi.fn().mockResolvedValue(null),
    discoverCapabilities: vi.fn().mockResolvedValue({ items: [], total: 0 }),
    resolveCapability: vi.fn().mockResolvedValue(null),
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
    getBalance: vi.fn().mockResolvedValue(overrides?.balance ?? {
      balance_usd: 25.50,
      balance_usd_cents: 2550,
      auto_reload_enabled: false,
    }),
    createCheckout: vi.fn().mockResolvedValue(overrides?.checkout ?? {
      checkout_url: "https://checkout.stripe.com/pay/cs_test_123",
      session_id: "cs_test_123",
    }),
    getLedger: vi.fn().mockResolvedValue(overrides?.ledger ?? {
      entries: [
        {
          id: "le_1",
          event_type: "debit",
          amount_usd_cents: -15,
          balance_after_usd_cents: 2535,
          description: "email.send via resend",
          created_at: "2026-03-17T10:00:00Z",
        },
        {
          id: "le_2",
          event_type: "credit_added",
          amount_usd_cents: 1000,
          balance_after_usd_cents: 2550,
          description: "Manual top-up",
          created_at: "2026-03-16T09:00:00Z",
        },
      ],
      total_count: 2,
    }),
  };
}

// ---------------------------------------------------------------------------
// check_balance
// ---------------------------------------------------------------------------

describe("check_balance handler", () => {
  it("returns correct structure with normal message when >= $1", async () => {
    const client = createMockClient();
    const result = await handleCheckBalance({}, client);

    expect(client.getBalance).toHaveBeenCalled();
    expect(result).toEqual({
      balance_usd: 25.50,
      balance_usd_cents: 2550,
      auto_reload_enabled: false,
      message: "Balance: $25.5",
    });
  });

  it("returns low-balance warning when < $1", async () => {
    const client = createMockClient({
      balance: {
        balance_usd: 0.45,
        balance_usd_cents: 45,
        auto_reload_enabled: false,
      },
    });
    const result = await handleCheckBalance({}, client);

    expect(result.balance_usd).toBe(0.45);
    expect(result.balance_usd_cents).toBe(45);
    expect(result.message).toContain("⚠️ Low balance");
    expect(result.message).toContain("$0.45");
    expect(result.message).toContain("https://rhumb.dev/pricing");
  });

  it("does not throw on API error — returns error in message", async () => {
    const client = createMockClient();
    (client.getBalance as ReturnType<typeof vi.fn>).mockRejectedValue(new Error("Balance check failed: 500"));

    const result = await handleCheckBalance({}, client);

    expect(result.balance_usd).toBe(0);
    expect(result.balance_usd_cents).toBe(0);
    expect(result.message).toContain("Failed to check balance");
    expect(result.message).toContain("500");
  });
});

// ---------------------------------------------------------------------------
// get_payment_url
// ---------------------------------------------------------------------------

describe("get_payment_url handler", () => {
  it("returns checkout URL for valid amount", async () => {
    const client = createMockClient();
    const result = await handleGetPaymentUrl({ amount_usd: 50 }, client);

    expect(client.createCheckout).toHaveBeenCalledWith(50);
    expect(result).toEqual({
      checkout_url: "https://checkout.stripe.com/pay/cs_test_123",
      amount_usd: 50,
      message: "Complete payment at: https://checkout.stripe.com/pay/cs_test_123",
    });
  });

  it("rejects amount below $5", async () => {
    const client = createMockClient();
    const result = await handleGetPaymentUrl({ amount_usd: 2 }, client);

    expect(client.createCheckout).not.toHaveBeenCalled();
    expect(result.checkout_url).toBe("");
    expect(result.amount_usd).toBe(2);
    expect(result.message).toContain("between $5 and $5,000");
    expect(result.message).toContain("$2");
  });

  it("rejects amount above $5000", async () => {
    const client = createMockClient();
    const result = await handleGetPaymentUrl({ amount_usd: 10000 }, client);

    expect(client.createCheckout).not.toHaveBeenCalled();
    expect(result.checkout_url).toBe("");
    expect(result.amount_usd).toBe(10000);
    expect(result.message).toContain("between $5 and $5,000");
  });

  it("does not throw on API error — returns error in message", async () => {
    const client = createMockClient();
    (client.createCheckout as ReturnType<typeof vi.fn>).mockRejectedValue(new Error("Checkout failed: 500"));

    const result = await handleGetPaymentUrl({ amount_usd: 50 }, client);

    expect(result.checkout_url).toBe("");
    expect(result.amount_usd).toBe(50);
    expect(result.message).toContain("Failed to create checkout");
  });
});

// ---------------------------------------------------------------------------
// get_ledger
// ---------------------------------------------------------------------------

describe("get_ledger handler", () => {
  it("returns entries with default limit", async () => {
    const client = createMockClient();
    const result = await handleGetLedger({}, client);

    expect(client.getLedger).toHaveBeenCalledWith(20, undefined);
    expect(result.entries).toHaveLength(2);
    expect(result.total_count).toBe(2);
    expect(result.entries[0]).toHaveProperty("id", "le_1");
    expect(result.entries[0]).toHaveProperty("event_type", "debit");
  });

  it("passes event_type filter", async () => {
    const client = createMockClient();
    await handleGetLedger({ event_type: "credit_added" }, client);

    expect(client.getLedger).toHaveBeenCalledWith(20, "credit_added");
  });

  it("clamps limit to minimum of 1", async () => {
    const client = createMockClient();
    await handleGetLedger({ limit: 0 }, client);

    expect(client.getLedger).toHaveBeenCalledWith(1, undefined);
  });

  it("clamps limit to maximum of 100", async () => {
    const client = createMockClient();
    await handleGetLedger({ limit: 500 }, client);

    expect(client.getLedger).toHaveBeenCalledWith(100, undefined);
  });

  it("does not throw on API error — returns empty", async () => {
    const client = createMockClient();
    (client.getLedger as ReturnType<typeof vi.fn>).mockRejectedValue(new Error("Ledger fetch failed: 500"));

    const result = await handleGetLedger({}, client);

    expect(result.entries).toEqual([]);
    expect(result.total_count).toBe(0);
  });
});

import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const ROOT_LLMS = readFileSync(new URL("../../../llms.txt", import.meta.url), "utf8");

describe("llms.txt contract", () => {
  it("matches the canonical root llms surface", () => {
    expect(ROOT_LLMS).toContain("resolve_capability");
    expect(ROOT_LLMS).toContain("estimate_capability");
    expect(ROOT_LLMS).toContain("active execution rail, cost, and health before execution");
    expect(ROOT_LLMS).toContain("machine-readable execute_readiness handoffs");
    expect(ROOT_LLMS).toContain("## Execution rails");
    expect(ROOT_LLMS).toContain("## Operator-controlled credential modes");
    expect(ROOT_LLMS).toContain("3 execution rails: governed API key, wallet-prefund, x402 / USDC");
    expect(ROOT_LLMS).toContain("2 operator-controlled credential modes where supported: BYOK, Agent Vault");
    expect(ROOT_LLMS).toContain("Execution rails: governed API key, wallet-prefund, or x402 per-call");
    expect(ROOT_LLMS).toContain("Provider-control modes where supported: BYOK and Agent Vault");
    expect(ROOT_LLMS).toContain("Agent Vault");
    expect(ROOT_LLMS).toContain("recovery_hint.resolve_url");
    expect(ROOT_LLMS).toContain("recovery_hint.credential_modes_url");
    expect(ROOT_LLMS).toContain("recovery_hint.alternate_execute_hint");
    expect(ROOT_LLMS).toContain("recovery_hint.setup_handoff");
    expect(ROOT_LLMS).not.toContain("## Auth paths");
    expect(ROOT_LLMS).not.toContain("3 credential modes: BYOK, Rhumb-managed, Agent Vault");
    expect(ROOT_LLMS).not.toContain("Execution: governed API key, wallet-prefund, x402 per-call, or BYOK");
    expect(ROOT_LLMS).not.toContain("machine-readable recovery handoffs");
    expect(ROOT_LLMS).not.toContain("GET https://api.rhumb.dev/v1/capabilities/{id}/execute/estimate — cost estimate");
    expect(ROOT_LLMS).not.toContain("estimate_cost");
    expect(ROOT_LLMS).not.toContain("get_budget_status");
  });
});

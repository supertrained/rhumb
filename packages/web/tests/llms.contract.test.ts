import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const ROOT_LLMS = readFileSync(new URL("../../../llms.txt", import.meta.url), "utf8");
const WEB_LLMS = readFileSync(new URL("../public/llms.txt", import.meta.url), "utf8");

describe("llms.txt contract", () => {
  it("matches the canonical root llms surface", () => {
    expect(WEB_LLMS).toBe(ROOT_LLMS);
    expect(WEB_LLMS).toContain("resolve_capability");
    expect(WEB_LLMS).toContain("estimate_capability");
    expect(WEB_LLMS).toContain("active execution rail, cost, and health before execution");
    expect(WEB_LLMS).toContain("machine-readable execute_readiness handoffs");
    expect(WEB_LLMS).toContain("## Execution rails");
    expect(WEB_LLMS).toContain("## Operator-controlled credential modes");
    expect(WEB_LLMS).toContain("Agent Vault");
    expect(WEB_LLMS).toContain("recovery_hint.resolve_url");
    expect(WEB_LLMS).toContain("recovery_hint.credential_modes_url");
    expect(WEB_LLMS).toContain("recovery_hint.alternate_execute_hint");
    expect(WEB_LLMS).toContain("recovery_hint.setup_handoff");
    expect(WEB_LLMS).not.toContain("## Auth paths");
    expect(WEB_LLMS).not.toContain("machine-readable recovery handoffs");
    expect(WEB_LLMS).not.toContain("GET https://api.rhumb.dev/v1/capabilities/{id}/execute/estimate — cost estimate");
    expect(WEB_LLMS).not.toContain("estimate_cost");
    expect(WEB_LLMS).not.toContain("get_budget_status");
  });
});

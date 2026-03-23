import { describe, it, expect } from "vitest";
import { createServer, getRegisteredToolNames } from "../src/server.js";

describe("server.init", () => {
  it("createServer returns a valid MCP server instance", () => {
    const server = createServer();
    expect(server).toBeDefined();
    // McpServer exposes a connect method
    expect(typeof server.connect).toBe("function");
  });

  it("server registers all 16 tools", () => {
    const names = getRegisteredToolNames();
    expect(names).toContain("find_services");
    expect(names).toContain("get_score");
    expect(names).toContain("get_alternatives");
    expect(names).toContain("get_failure_modes");
    expect(names).toContain("discover_capabilities");
    expect(names).toContain("resolve_capability");
    expect(names).toContain("execute_capability");
    expect(names).toContain("estimate_capability");
    expect(names).toContain("credential_ceremony");
    expect(names).toContain("check_credentials");
    expect(names).toContain("budget");
    expect(names).toContain("spend");
    expect(names).toContain("routing");
    expect(names).toContain("check_balance");
    expect(names).toContain("get_payment_url");
    expect(names).toContain("get_ledger");
    expect(names).toHaveLength(16);
  });
});

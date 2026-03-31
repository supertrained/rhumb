import { describe, it, expect } from "vitest";
import { createServer, getRegisteredToolNames } from "../src/server.js";

describe("server.init", () => {
  it("createServer returns a valid MCP server instance", () => {
    const server = createServer();
    expect(server).toBeDefined();
    // McpServer exposes a connect method
    expect(typeof server.connect).toBe("function");
  });

  it("server registers all 21 tools", () => {
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
    expect(names).toContain("usage_telemetry");
    expect(names).toContain("check_balance");
    expect(names).toContain("get_payment_url");
    expect(names).toContain("get_ledger");
    expect(names).toContain("rhumb_list_recipes");
    expect(names).toContain("rhumb_get_recipe");
    expect(names).toContain("rhumb_recipe_execute");
    expect(names).toContain("get_receipt");
    expect(names).toHaveLength(21);
  });
});

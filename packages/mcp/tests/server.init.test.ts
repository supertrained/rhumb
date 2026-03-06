import { describe, it, expect } from "vitest";
import { createServer, getRegisteredToolNames } from "../src/server.js";

describe("server.init", () => {
  it("createServer returns a valid MCP server instance", () => {
    const server = createServer();
    expect(server).toBeDefined();
    // McpServer exposes a connect method
    expect(typeof server.connect).toBe("function");
  });

  it("server registers all 4 tools", () => {
    const names = getRegisteredToolNames();
    expect(names).toContain("find_tools");
    expect(names).toContain("get_score");
    expect(names).toContain("get_alternatives");
    expect(names).toContain("get_failure_modes");
    expect(names).toHaveLength(4);
  });
});

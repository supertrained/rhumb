#!/usr/bin/env node
/**
 * Rhumb MCP Server — Entry point (stdio transport)
 *
 * Usage:
 *   npx tsx src/index.ts          # development
 *   node dist/index.js            # production (after tsc build)
 *
 * The server communicates over stdio using the Model Context Protocol.
 */

import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { createServer } from "./server.js";

async function main() {
  const server = createServer();
  const transport = new StdioServerTransport();
  await server.connect(transport);
  // Server now listens on stdin/stdout — blocks until transport closes
}

main().catch((err) => {
  console.error("Rhumb MCP server failed to start:", err);
  process.exit(1);
});

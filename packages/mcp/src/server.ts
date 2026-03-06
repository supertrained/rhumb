/**
 * Rhumb MCP Server — Server initialization and tool registration
 */

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import {
  TOOL_NAMES,
  FindToolInputSchema,
  GetScoreInputSchema,
  GetAlternativesInputSchema,
  GetFailureModesInputSchema
} from "./types.js";

/**
 * Creates and configures the Rhumb MCP server with all tool registrations.
 * Tool handlers are stubs in Slice A — real implementations come in Slices B/C.
 */
export function createServer(): McpServer {
  const server = new McpServer({
    name: "rhumb",
    version: "0.0.1"
  });

  // -- find_tools --------------------------------------------------------
  server.tool(
    "find_tools",
    "Semantic search for agent tools, ranked by AN Score",
    {
      query: z.string().describe(FindToolInputSchema.properties.query.description),
      limit: z.number().min(1).max(50).optional().describe(FindToolInputSchema.properties.limit.description)
    },
    async ({ query, limit }) => {
      // Stub — Slice B implements real handler
      return {
        content: [{ type: "text" as const, text: JSON.stringify({ tools: [] }) }]
      };
    }
  );

  // -- get_score ---------------------------------------------------------
  server.tool(
    "get_score",
    "Get detailed AN Score breakdown for a service",
    {
      slug: z.string().describe(GetScoreInputSchema.properties.slug.description)
    },
    async ({ slug }) => {
      // Stub — Slice B implements real handler
      return {
        content: [{ type: "text" as const, text: JSON.stringify({ slug, aggregateScore: null, executionScore: null, accessScore: null, confidence: 0, tier: "unknown", explanation: "Not yet implemented", freshness: "unknown" }) }]
      };
    }
  );

  // -- get_alternatives --------------------------------------------------
  server.tool(
    "get_alternatives",
    "Find alternative services ranked by AN Score",
    {
      slug: z.string().describe(GetAlternativesInputSchema.properties.slug.description)
    },
    async ({ slug }) => {
      // Stub — Slice C implements real handler
      return {
        content: [{ type: "text" as const, text: JSON.stringify({ alternatives: [] }) }]
      };
    }
  );

  // -- get_failure_modes -------------------------------------------------
  server.tool(
    "get_failure_modes",
    "Get known failure patterns for a service",
    {
      slug: z.string().describe(GetFailureModesInputSchema.properties.slug.description)
    },
    async ({ slug }) => {
      // Stub — Slice C implements real handler
      return {
        content: [{ type: "text" as const, text: JSON.stringify({ failures: [] }) }]
      };
    }
  );

  return server;
}

/**
 * Returns the list of registered tool names.
 * Useful for verification without accessing MCP internals.
 */
export function getRegisteredToolNames(): string[] {
  return [...TOOL_NAMES];
}

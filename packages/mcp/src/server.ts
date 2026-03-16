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
  GetFailureModesInputSchema,
  DiscoverCapabilitiesInputSchema,
  ResolveCapabilityInputSchema
} from "./types.js";
import { createApiClient, type RhumbApiClient } from "./api-client.js";
import { handleFindTools } from "./tools/find.js";
import { handleGetScore } from "./tools/score.js";
import { handleGetAlternatives } from "./tools/alternatives.js";
import { handleGetFailureModes } from "./tools/failures.js";
import { handleDiscoverCapabilities } from "./tools/capabilities.js";
import { handleResolveCapability } from "./tools/resolve.js";

/**
 * Creates and configures the Rhumb MCP server with all tool registrations.
 *
 * @param apiClient Optional API client override (for testing). Uses default
 *                  createApiClient() when omitted.
 */
export function createServer(apiClient?: RhumbApiClient): McpServer {
  const client = apiClient ?? createApiClient();

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
      const result = await handleFindTools({ query, limit }, client);
      return {
        content: [{ type: "text" as const, text: JSON.stringify(result) }]
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
      const result = await handleGetScore({ slug }, client);
      return {
        content: [{ type: "text" as const, text: JSON.stringify(result) }]
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
      const result = await handleGetAlternatives({ slug }, client);
      return {
        content: [{ type: "text" as const, text: JSON.stringify(result) }]
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
      const result = await handleGetFailureModes({ slug }, client);
      return {
        content: [{ type: "text" as const, text: JSON.stringify(result) }]
      };
    }
  );

  // -- discover_capabilities ----------------------------------------------
  server.tool(
    "discover_capabilities",
    "Discover what capabilities are available — search by domain or text. Returns capabilities with provider counts and top provider info.",
    {
      domain: z.string().optional().describe(DiscoverCapabilitiesInputSchema.properties.domain.description),
      search: z.string().optional().describe(DiscoverCapabilitiesInputSchema.properties.search.description),
      limit: z.number().min(1).max(50).optional().describe(DiscoverCapabilitiesInputSchema.properties.limit.description)
    },
    async ({ domain, search, limit }) => {
      const result = await handleDiscoverCapabilities({ domain, search, limit }, client);
      return {
        content: [{ type: "text" as const, text: JSON.stringify(result) }]
      };
    }
  );

  // -- resolve_capability ------------------------------------------------
  server.tool(
    "resolve_capability",
    "Resolve a capability to ranked providers with health-aware recommendations, costs, and fallback chains. The core agent decision: 'I need email.send — what should I use?'",
    {
      capability: z.string().describe(ResolveCapabilityInputSchema.properties.capability.description)
    },
    async ({ capability }) => {
      const result = await handleResolveCapability({ capability }, client);
      return {
        content: [{ type: "text" as const, text: JSON.stringify(result) }]
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

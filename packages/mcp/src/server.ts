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
  ResolveCapabilityInputSchema,
  ExecuteCapabilityInputSchema,
  EstimateCapabilityInputSchema,
  CredentialCeremonyInputSchema,
  CheckCredentialsInputSchema
} from "./types.js";
import { createApiClient, type RhumbApiClient } from "./api-client.js";
import { handleFindTools } from "./tools/find.js";
import { handleGetScore } from "./tools/score.js";
import { handleGetAlternatives } from "./tools/alternatives.js";
import { handleGetFailureModes } from "./tools/failures.js";
import { handleDiscoverCapabilities } from "./tools/capabilities.js";
import { handleResolveCapability } from "./tools/resolve.js";
import { handleExecuteCapability } from "./tools/execute.js";
import { handleEstimateCapability } from "./tools/estimate.js";
import { handleCredentialCeremony } from "./tools/ceremony.js";
import { handleCheckCredentials } from "./tools/credentials.js";

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

  // -- execute_capability ------------------------------------------------
  server.tool(
    "execute_capability",
    "Execute a capability through Rhumb. Three credential modes: (1) byo — bring your own token, requires method+path; (2) rhumb_managed — zero-config, Rhumb provides credentials, method/path optional; (3) agent_vault — pass your own token via agent_token param (get it from credential_ceremony first). Use resolve_capability to see providers and check_credentials to see what modes are available.",
    {
      capability_id: z.string().describe(ExecuteCapabilityInputSchema.properties.capability_id.description),
      provider: z.string().optional().describe(ExecuteCapabilityInputSchema.properties.provider.description),
      method: z.string().optional().describe(ExecuteCapabilityInputSchema.properties.method.description),
      path: z.string().optional().describe(ExecuteCapabilityInputSchema.properties.path.description),
      body: z.record(z.string(), z.unknown()).optional().describe(ExecuteCapabilityInputSchema.properties.body.description),
      params: z.record(z.string(), z.string()).optional().describe(ExecuteCapabilityInputSchema.properties.params.description),
      credential_mode: z.string().optional().describe(ExecuteCapabilityInputSchema.properties.credential_mode.description),
      idempotency_key: z.string().optional().describe(ExecuteCapabilityInputSchema.properties.idempotency_key.description),
      agent_token: z.string().optional().describe(ExecuteCapabilityInputSchema.properties.agent_token.description)
    },
    async ({ capability_id, provider, method, path, body, params, credential_mode, idempotency_key, agent_token }) => {
      const result = await handleExecuteCapability(
        { capability_id, provider, method, path, body, params, credential_mode, idempotency_key, agent_token },
        client
      );
      return {
        content: [{ type: "text" as const, text: JSON.stringify(result) }]
      };
    }
  );

  // -- estimate_capability -----------------------------------------------
  server.tool(
    "estimate_capability",
    "Get cost estimate for executing a capability without actually executing it. Use before expensive operations or when building cost-aware workflows.",
    {
      capability_id: z.string().describe(EstimateCapabilityInputSchema.properties.capability_id.description),
      provider: z.string().optional().describe(EstimateCapabilityInputSchema.properties.provider.description),
      credential_mode: z.string().optional().describe(EstimateCapabilityInputSchema.properties.credential_mode.description)
    },
    async ({ capability_id, provider, credential_mode }) => {
      const result = await handleEstimateCapability(
        { capability_id, provider, credential_mode },
        client
      );
      return {
        content: [{ type: "text" as const, text: JSON.stringify(result) }]
      };
    }
  );

  // -- credential_ceremony ------------------------------------------------
  server.tool(
    "credential_ceremony",
    "Get step-by-step instructions for obtaining API credentials for a service. Without a service param, lists all available ceremonies. With a service param, returns detailed steps, token format info, and documentation links. Use this before agent_vault execute mode.",
    {
      service: z.string().optional().describe(CredentialCeremonyInputSchema.properties.service.description)
    },
    async ({ service }) => {
      const result = await handleCredentialCeremony({ service }, client);
      return {
        content: [{ type: "text" as const, text: JSON.stringify(result) }]
      };
    }
  );

  // -- check_credentials ------------------------------------------------
  server.tool(
    "check_credentials",
    "Check your credential status across all three modes. Shows which capabilities are available via Rhumb-managed (zero-config), which services have ceremony guides for self-provisioning, and BYO status. Start here to understand what you can execute.",
    {
      capability: z.string().optional().describe(CheckCredentialsInputSchema.properties.capability.description)
    },
    async ({ capability }) => {
      const result = await handleCheckCredentials({ capability }, client);
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

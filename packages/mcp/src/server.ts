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
  CheckCredentialsInputSchema,
  BudgetInputSchema,
  SpendInputSchema,
  RoutingInputSchema
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
import { handleBudget } from "./tools/budget.js";
import { handleSpend } from "./tools/spend.js";
import { handleRouting } from "./tools/routing.js";
import { handleCheckBalance } from "./tools/check-balance.js";
import { handleGetPaymentUrl } from "./tools/get-payment-url.js";
import { handleGetLedger } from "./tools/get-ledger.js";

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
    "Search for services/APIs by what you need them to do. Returns ranked results with AN Scores (agent-nativeness ratings). Use this when you know the problem but not which service to use. For capability-level search (e.g. 'email.send'), use discover_capabilities instead.",
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
    "Get the full AN Score breakdown for a service: execution quality, access readiness, autonomy level, tier label, and freshness. Use after find_tools to evaluate a specific service.",
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
    "Find alternatives to a service, ranked by AN Score. Use when a service doesn't meet your needs or you want to compare options in the same category.",
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
    "Get known failure patterns, impact severity, and workarounds for a service. Use BEFORE integrating to write defensive code, or AFTER hitting an error to diagnose it.",
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
    "Browse capabilities by domain or search text. A capability is an action (e.g. 'email.send', 'payment.charge') that multiple providers can fulfill. Use this when you know WHAT you need to do but not which service does it. Returns capability IDs for resolve_capability. Different from find_tools: find_tools searches services, this searches capabilities.",
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
    "Given a capability ID, returns ranked providers with health status, cost per call, auth methods, endpoint patterns, and fallback chains. This is the core routing decision: 'I need email.send — which provider should I use?' Call this before execute_capability to understand your options.",
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
    "Execute a capability through Rhumb's proxy. Typical workflow: discover_capabilities → resolve_capability → estimate_capability → execute_capability. Three credential modes: (1) rhumb_managed — simplest, zero-config, Rhumb provides credentials (just pass capability_id); (2) byo — bring your own API key via agent_token + method + path; (3) agent_vault — use a key from credential_ceremony via agent_token + method + path. Alternative: pass x_payment for per-call USDC payment with no account needed. Use check_credentials to see which modes are available.",
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
    "Get the cost of executing a capability WITHOUT actually executing it. Returns cost in USD, circuit health, and endpoint pattern. Always call this before execute_capability for cost-sensitive workflows — no charge for estimates.",
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
    "Get step-by-step instructions to obtain API credentials for a service. Returns signup steps, expected token format (prefix, pattern), verification endpoint, estimated time, and whether human intervention is needed. Use before executing in agent_vault mode. Call without params to list all services with available ceremonies.",
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
    "Check what credential modes are available to you. Shows: (1) which capabilities have Rhumb-managed credentials (ready to execute immediately), (2) which services have ceremony guides (self-provision in minutes), and (3) BYO status. Start here when you're new to Rhumb or unsure what you can execute.",
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

  // -- budget -----------------------------------------------------------
  server.tool(
    "budget",
    "Check or set your execution spending limit. Budgets are enforced BEFORE execution — you get HTTP 402 (not a surprise bill) when you'd exceed your limit. Call with no params to check current budget and remaining balance.",
    {
      action: z.string().optional().describe(BudgetInputSchema.properties.action.description),
      budget_usd: z.number().optional().describe(BudgetInputSchema.properties.budget_usd.description),
      period: z.string().optional().describe(BudgetInputSchema.properties.period.description),
      hard_limit: z.boolean().optional().describe(BudgetInputSchema.properties.hard_limit.description)
    },
    async ({ action, budget_usd, period, hard_limit }) => {
      const result = await handleBudget({ action, budget_usd, period, hard_limit }, client);
      return {
        content: [{ type: "text" as const, text: JSON.stringify(result) }]
      };
    }
  );

  // -- spend ------------------------------------------------------------
  server.tool(
    "spend",
    "Get your spending breakdown for a billing period: total USD spent, execution count, average cost per call, broken down by capability and by provider. Use to audit costs or optimize routing.",
    {
      period: z.string().optional().describe(SpendInputSchema.properties.period.description)
    },
    async ({ period }) => {
      const result = await handleSpend({ period }, client);
      return {
        content: [{ type: "text" as const, text: JSON.stringify(result) }]
      };
    }
  );

  // -- routing ----------------------------------------------------------
  server.tool(
    "routing",
    "Get or set how Rhumb auto-selects providers when you don't specify one in execute_capability. Controls the tradeoff between cost, speed, and quality. Also sets a quality floor (minimum AN Score) and optional per-call cost ceiling.",
    {
      action: z.string().optional().describe(RoutingInputSchema.properties.action.description),
      strategy: z.string().optional().describe(RoutingInputSchema.properties.strategy.description),
      quality_floor: z.number().optional().describe(RoutingInputSchema.properties.quality_floor.description),
      max_cost_per_call_usd: z.number().optional().describe(RoutingInputSchema.properties.max_cost_per_call_usd.description)
    },
    async ({ action, strategy, quality_floor, max_cost_per_call_usd }) => {
      const result = await handleRouting({ action, strategy, quality_floor, max_cost_per_call_usd }, client);
      return {
        content: [{ type: "text" as const, text: JSON.stringify(result) }]
      };
    }
  );

  // -- check_balance -----------------------------------------------------
  server.tool(
    "check_balance",
    "Check your current Rhumb credit balance in USD. Also shows whether auto-reload is enabled. If balance is low, use get_payment_url to top up.",
    {},
    async () => {
      const result = await handleCheckBalance({}, client);
      return {
        content: [{ type: "text" as const, text: JSON.stringify(result) }]
      };
    }
  );

  // -- get_payment_url ---------------------------------------------------
  server.tool(
    "get_payment_url",
    "Get a checkout URL to add credits to your Rhumb balance. Present this URL to a human to complete payment. Credits are available immediately after payment.",
    {
      amount_usd: z.number().min(5).max(5000).describe("Amount to add in USD (min $5, max $5000)")
    },
    async ({ amount_usd }) => {
      const result = await handleGetPaymentUrl({ amount_usd }, client);
      return {
        content: [{ type: "text" as const, text: JSON.stringify(result) }]
      };
    }
  );

  // -- get_ledger --------------------------------------------------------
  server.tool(
    "get_ledger",
    "Get your billing history: charges (debits), top-ups (credits), and auto-reload events. Each entry shows amount, balance after, description, and timestamp. Most recent first.",
    {
      limit: z.number().min(1).max(100).optional().describe("Number of entries (default 20, max 100)"),
      event_type: z.string().optional().describe("Filter: debit, credit_added, auto_reload_triggered")
    },
    async ({ limit, event_type }) => {
      const result = await handleGetLedger({ limit, event_type }, client);
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

/**
 * Rhumb MCP Server — Tool I/O Contracts
 *
 * All tool inputs/outputs are defined as JSON Schema objects
 * alongside their TypeScript type equivalents.
 */

// ---------------------------------------------------------------------------
// find_tools
// ---------------------------------------------------------------------------

export const FindToolInputSchema = {
  type: "object" as const,
  properties: {
    query: { type: "string" as const, description: "Semantic search query for tool discovery" },
    limit: { type: "number" as const, minimum: 1, maximum: 50, description: "Max results to return (default 10)" }
  },
  required: ["query"] as const
};

export type FindToolInput = {
  query: string;
  limit?: number;
};

export type FindToolOutput = {
  tools: Array<{
    name: string;
    slug: string;
    aggregateScore: number | null;
    executionScore: number | null;
    accessScore: number | null;
    explanation: string;
  }>;
};

// ---------------------------------------------------------------------------
// get_score
// ---------------------------------------------------------------------------

export const GetScoreInputSchema = {
  type: "object" as const,
  properties: {
    slug: { type: "string" as const, description: "Service slug to look up" }
  },
  required: ["slug"] as const
};

export type GetScoreInput = {
  slug: string;
};

export type GetScoreOutput = {
  slug: string;
  aggregateScore: number | null;
  executionScore: number | null;
  accessScore: number | null;
  confidence: number;
  tier: string;
  explanation: string;
  freshness: string;
};

// ---------------------------------------------------------------------------
// get_alternatives
// ---------------------------------------------------------------------------

export const GetAlternativesInputSchema = {
  type: "object" as const,
  properties: {
    slug: { type: "string" as const, description: "Service slug to find alternatives for" }
  },
  required: ["slug"] as const
};

export type GetAlternativesInput = {
  slug: string;
};

export type GetAlternativesOutput = {
  alternatives: Array<{
    name: string;
    slug: string;
    aggregateScore: number | null;
    reason: string;
  }>;
};

// ---------------------------------------------------------------------------
// get_failure_modes
// ---------------------------------------------------------------------------

export const GetFailureModesInputSchema = {
  type: "object" as const,
  properties: {
    slug: { type: "string" as const, description: "Service slug to get failure modes for" }
  },
  required: ["slug"] as const
};

export type GetFailureModesInput = {
  slug: string;
};

export type GetFailureModesOutput = {
  failures: Array<{
    pattern: string;
    impact: string;
    frequency: string;
    workaround: string;
  }>;
};

// ---------------------------------------------------------------------------
// discover_capabilities
// ---------------------------------------------------------------------------

export const DiscoverCapabilitiesInputSchema = {
  type: "object" as const,
  properties: {
    domain: { type: "string" as const, description: "Filter by capability domain (e.g. 'email', 'payment', 'ai')" },
    search: { type: "string" as const, description: "Search capabilities by text" },
    limit: { type: "number" as const, minimum: 1, maximum: 50, description: "Max results to return (default 20)" }
  },
  required: [] as const
};

export type DiscoverCapabilitiesInput = {
  domain?: string;
  search?: string;
  limit?: number;
};

export type CapabilityItem = {
  id: string;
  domain: string;
  action: string;
  description: string;
  inputHint: string;
  outcome: string;
  providerCount: number;
  topProvider: { slug: string; anScore: number | null; tierLabel: string } | null;
};

export type DiscoverCapabilitiesOutput = {
  capabilities: CapabilityItem[];
  total: number;
};

// ---------------------------------------------------------------------------
// resolve_capability
// ---------------------------------------------------------------------------

export const ResolveCapabilityInputSchema = {
  type: "object" as const,
  properties: {
    capability: { type: "string" as const, description: "Capability ID to resolve (e.g. 'email.send', 'payment.charge')" }
  },
  required: ["capability"] as const
};

export type ResolveCapabilityInput = {
  capability: string;
};

export type CapabilityProvider = {
  serviceSlug: string;
  serviceName: string;
  anScore: number | null;
  costPerCall: number | null;
  freeTierCalls: number | null;
  authMethod: string;
  endpointPattern: string;
  recommendation: string;
  recommendationReason: string;
};

export type ResolveCapabilityOutput = {
  capability: string;
  providers: CapabilityProvider[];
  fallbackChain: string[];
  relatedBundles: string[];
};

// ---------------------------------------------------------------------------
// Schema registry — all tool schemas in one place
// ---------------------------------------------------------------------------

export const TOOL_SCHEMAS = {
  find_tools: FindToolInputSchema,
  get_score: GetScoreInputSchema,
  get_alternatives: GetAlternativesInputSchema,
  get_failure_modes: GetFailureModesInputSchema,
  discover_capabilities: DiscoverCapabilitiesInputSchema,
  resolve_capability: ResolveCapabilityInputSchema
} as const;

export const TOOL_NAMES = Object.keys(TOOL_SCHEMAS) as Array<keyof typeof TOOL_SCHEMAS>;

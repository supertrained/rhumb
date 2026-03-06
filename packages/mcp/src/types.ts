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
// Schema registry — all tool schemas in one place
// ---------------------------------------------------------------------------

export const TOOL_SCHEMAS = {
  find_tools: FindToolInputSchema,
  get_score: GetScoreInputSchema,
  get_alternatives: GetAlternativesInputSchema,
  get_failure_modes: GetFailureModesInputSchema
} as const;

export const TOOL_NAMES = Object.keys(TOOL_SCHEMAS) as Array<keyof typeof TOOL_SCHEMAS>;

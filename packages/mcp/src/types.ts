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
// execute_capability
// ---------------------------------------------------------------------------

export const ExecuteCapabilityInputSchema = {
  type: "object" as const,
  properties: {
    capability_id: { type: "string" as const, description: "Capability to execute (e.g. 'email.send', 'payment.charge')" },
    provider: { type: "string" as const, description: "Optional: specific provider slug. If omitted, Rhumb auto-selects the best healthy provider." },
    method: { type: "string" as const, description: "HTTP method for the upstream API call (GET, POST, PUT, PATCH, DELETE)" },
    path: { type: "string" as const, description: "Provider-native API path (e.g. '/v3/mail/send'). Use resolve_capability first to get the endpoint pattern." },
    body: { type: "object" as const, description: "Provider-native request body" },
    params: { type: "object" as const, description: "Optional query parameters" },
    credential_mode: { type: "string" as const, description: "Credential mode: byo (default), rhumb_managed (zero-config, omit method/path), or agent_vault (pass agent_token)" },
    idempotency_key: { type: "string" as const, description: "Optional UUID for safe retry. Required to enable automatic fallback to backup providers." },
    agent_token: { type: "string" as const, description: "For agent_vault mode only: the API token you obtained via the credential ceremony. NEVER stored by Rhumb — used for this single request only." }
  },
  required: ["capability_id"] as const
};

export type ExecuteCapabilityInput = {
  capability_id: string;
  provider?: string;
  method?: string;
  path?: string;
  body?: Record<string, unknown>;
  params?: Record<string, string>;
  credential_mode?: string;
  idempotency_key?: string;
  agent_token?: string;
};

export type ExecuteCapabilityOutput = {
  capabilityId: string;
  providerUsed: string;
  credentialMode: string;
  upstreamStatus: number | null;
  upstreamResponse: unknown;
  costEstimateUsd: number | null;
  latencyMs: number | null;
  fallbackAttempted: boolean;
  fallbackProvider: string | null;
  executionId: string;
  deduplicated?: boolean;
};

// ---------------------------------------------------------------------------
// estimate_capability
// ---------------------------------------------------------------------------

export const EstimateCapabilityInputSchema = {
  type: "object" as const,
  properties: {
    capability_id: { type: "string" as const, description: "Capability to estimate cost for (e.g. 'email.send')" },
    provider: { type: "string" as const, description: "Optional: specific provider. If omitted, estimates for the auto-selected provider." },
    credential_mode: { type: "string" as const, description: "Credential mode: byo (default), rhumb_managed, or agent_vault" }
  },
  required: ["capability_id"] as const
};

export type EstimateCapabilityInput = {
  capability_id: string;
  provider?: string;
  credential_mode?: string;
};

export type EstimateCapabilityOutput = {
  capabilityId: string;
  provider: string;
  credentialMode: string;
  costEstimateUsd: number | null;
  circuitState: string;
  endpointPattern: string | null;
};

// ---------------------------------------------------------------------------
// credential_ceremony
// ---------------------------------------------------------------------------

export const CredentialCeremonyInputSchema = {
  type: "object" as const,
  properties: {
    service: { type: "string" as const, description: "Service slug to get the credential ceremony for (e.g. 'openai', 'stripe', 'resend'). Omit to list all available ceremonies." }
  },
  required: [] as const
};

export type CredentialCeremonyInput = {
  service?: string;
};

export type CeremonyStep = {
  step: number;
  action: string;
  type: string;
};

export type CeremonySummary = {
  service: string;
  displayName: string;
  description: string;
  authType: string;
  difficulty: string;
  estimatedMinutes: number;
  requiresHuman: boolean;
  documentationUrl: string | null;
};

export type CeremonyDetail = CeremonySummary & {
  steps: CeremonyStep[];
  tokenPrefix: string | null;
  tokenPattern: string | null;
  verifyEndpoint: string | null;
};

export type CredentialCeremonyOutput = {
  ceremony?: CeremonyDetail;
  ceremonies?: CeremonySummary[];
  count: number;
};

// ---------------------------------------------------------------------------
// check_credentials
// ---------------------------------------------------------------------------

export const CheckCredentialsInputSchema = {
  type: "object" as const,
  properties: {
    capability: { type: "string" as const, description: "Optional: check credential status for a specific capability (e.g. 'email.send')" }
  },
  required: [] as const
};

export type CheckCredentialsInput = {
  capability?: string;
};

export type CredentialModeStatus = {
  mode: string;
  available: boolean;
  detail: string;
};

export type CheckCredentialsOutput = {
  modes: CredentialModeStatus[];
  managedCapabilities: Array<{
    capabilityId: string;
    service: string;
    description: string;
  }>;
  availableCeremonies: number;
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
  resolve_capability: ResolveCapabilityInputSchema,
  execute_capability: ExecuteCapabilityInputSchema,
  estimate_capability: EstimateCapabilityInputSchema,
  credential_ceremony: CredentialCeremonyInputSchema,
  check_credentials: CheckCredentialsInputSchema
} as const;

export const TOOL_NAMES = Object.keys(TOOL_SCHEMAS) as Array<keyof typeof TOOL_SCHEMAS>;

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
    query: { type: "string" as const, description: "What you need the tool to do, in natural language. Examples: 'send email', 'process payments', 'generate images', 'web scraping'" },
    limit: { type: "number" as const, minimum: 1, maximum: 50, description: "Max results (default 10). Each result includes a slug you can pass to get_score, get_alternatives, or get_failure_modes." }
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
    slug: { type: "string" as const, description: "Service identifier from find_tools results (e.g. 'stripe', 'sendgrid', 'openai', 'twilio')" }
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
    slug: { type: "string" as const, description: "Service slug from find_tools results (e.g. 'stripe'). Returns other services in the same category, ranked by AN Score." }
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
    slug: { type: "string" as const, description: "Service slug from find_tools results (e.g. 'stripe'). Returns known failure patterns, impact severity, and workarounds." }
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
    domain: { type: "string" as const, description: "Filter by domain: 'email', 'payment', 'ai', 'communication', 'data', 'storage', 'search', etc. Omit for all domains." },
    search: { type: "string" as const, description: "Free-text search across capability names and descriptions. Examples: 'send message', 'charge card', 'scrape website'" },
    limit: { type: "number" as const, minimum: 1, maximum: 50, description: "Max results (default 20). Returns capability IDs you can pass to resolve_capability." }
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
    capability: { type: "string" as const, description: "Capability ID from discover_capabilities (e.g. 'email.send', 'payment.charge'). Returns ranked providers with costs, health status, and fallback chains." }
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
    capability_id: { type: "string" as const, description: "Capability to execute (e.g. 'email.send', 'payment.charge'). Get IDs from discover_capabilities or resolve_capability." },
    provider: { type: "string" as const, description: "Specific provider slug (e.g. 'resend', 'stripe'). Omit to let Rhumb auto-select the best healthy provider based on your routing strategy." },
    method: { type: "string" as const, description: "HTTP method (GET, POST, PUT, PATCH, DELETE). Required for byo and agent_vault modes. Not needed for rhumb_managed." },
    path: { type: "string" as const, description: "Provider's API path (e.g. '/v3/mail/send'). Get the pattern from resolve_capability. Required for byo/agent_vault. Not needed for rhumb_managed." },
    body: { type: "object" as const, description: "Request body in the provider's native format. See provider docs or resolve_capability for expected structure." },
    params: { type: "object" as const, description: "URL query parameters as key-value pairs" },
    credential_mode: { type: "string" as const, description: "'rhumb_managed' (zero-config, Rhumb provides credentials — simplest), 'byo' (your own API key via agent_token — requires method+path), or 'agent_vault' (key from credential_ceremony — requires method+path). Default: byo" },
    idempotency_key: { type: "string" as const, description: "UUID for safe retry — if this request was already processed, returns the cached result instead of re-executing. Required to enable automatic fallback to backup providers on failure." },
    agent_token: { type: "string" as const, description: "Your API token for byo/agent_vault mode. For agent_vault: obtain via credential_ceremony first. Never stored by Rhumb — used for this single request only." },
    x_payment: { type: "string" as const, description: "x402 payment proof (base64 or JSON). Use this to pay per-call with USDC instead of an API key. Pass the proof from a payment_required (402) response. No account or signup needed." }
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
  x_payment?: string;
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
  /** Present when HTTP 402 is returned. Contains x402 payment instructions. */
  paymentRequired?: X402PaymentInfo;
};

/** x402 payment instructions returned on HTTP 402 */
export type X402PaymentInfo = {
  x402Version: number;
  accepts: Array<Record<string, unknown>>;
  error: string;
  balanceRequired: number;
  balanceRequiredUsd: number;
};

// ---------------------------------------------------------------------------
// estimate_capability
// ---------------------------------------------------------------------------

export const EstimateCapabilityInputSchema = {
  type: "object" as const,
  properties: {
    capability_id: { type: "string" as const, description: "Capability to estimate (e.g. 'email.send'). Call this BEFORE execute_capability to know the cost in advance." },
    provider: { type: "string" as const, description: "Specific provider slug. Omit to estimate for the auto-selected provider based on your routing strategy." },
    credential_mode: { type: "string" as const, description: "'rhumb_managed', 'byo', or 'agent_vault'. Affects pricing — rhumb_managed includes a 20% markup." }
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
    service: { type: "string" as const, description: "Service slug (e.g. 'openai', 'stripe', 'resend'). Returns step-by-step signup instructions, expected token format, and verification endpoint. Omit to list all services with available ceremonies." }
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
    capability: { type: "string" as const, description: "Check a specific capability (e.g. 'email.send'). Omit to see all modes and managed capabilities. Start here to understand what you can execute and how." }
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
// budget
// ---------------------------------------------------------------------------

export const BudgetInputSchema = {
  type: "object" as const,
  properties: {
    action: { type: "string" as const, description: "'get' (check current budget) or 'set' (create/update). Default: 'get'" },
    budget_usd: { type: "number" as const, description: "Budget cap in USD. Required when action='set'. Example: 10.00 for $10/month." },
    period: { type: "string" as const, description: "'daily', 'weekly', 'monthly', or 'total'. Default: 'monthly'. Resets at period boundary." },
    hard_limit: { type: "boolean" as const, description: "true = reject executions over budget with HTTP 402. false = warn but allow. Default: true" }
  },
  required: [] as const
};

export type BudgetInput = {
  action?: string;
  budget_usd?: number;
  period?: string;
  hard_limit?: boolean;
};

export type BudgetOutput = {
  agent_id: string;
  budget_usd: number | null;
  spent_usd: number | null;
  remaining_usd: number | null;
  period: string | null;
  hard_limit: boolean | null;
  unlimited: boolean;
};

// ---------------------------------------------------------------------------
// spend
// ---------------------------------------------------------------------------

export const SpendInputSchema = {
  type: "object" as const,
  properties: {
    period: { type: "string" as const, description: "Billing period as YYYY-MM (e.g. '2026-03'). Defaults to current month. Returns per-capability and per-provider spend breakdown." }
  },
  required: [] as const
};

export type SpendInput = {
  period?: string;
};

export type SpendOutput = {
  agent_id: string;
  period: string;
  total_spend_usd: number;
  total_executions: number;
  by_capability: Array<{
    capability_id: string;
    spend_usd: number;
    executions: number;
    avg_cost: number;
  }>;
  by_provider: Array<{
    provider: string;
    spend_usd: number;
    executions: number;
  }>;
};

// ---------------------------------------------------------------------------
// routing
// ---------------------------------------------------------------------------

export const RoutingInputSchema = {
  type: "object" as const,
  properties: {
    action: { type: "string" as const, description: "'get' (check current strategy) or 'set' (update). Default: 'get'" },
    strategy: { type: "string" as const, description: "'cheapest' (lowest cost above quality floor), 'fastest' (healthiest circuits, lowest latency), 'highest_quality' (highest AN Score), or 'balanced' (weighted mix of all three). Default: 'balanced'" },
    quality_floor: { type: "number" as const, description: "Minimum AN Score (0-10). Providers below this are excluded from auto-selection. Default: 6.0" },
    max_cost_per_call_usd: { type: "number" as const, description: "Hard ceiling on per-call cost. Calls that would exceed this are rejected with 402." }
  },
  required: [] as const
};

export type RoutingInput = {
  action?: string;
  strategy?: string;
  quality_floor?: number;
  max_cost_per_call_usd?: number;
};

export type RoutingOutput = {
  agent_id: string;
  strategy: string;
  quality_floor: number;
  max_cost_per_call_usd: number | null;
  weight_score: number;
  weight_cost: number;
  weight_health: number;
};

// ---------------------------------------------------------------------------
// check_balance
// ---------------------------------------------------------------------------

export const CheckBalanceInputSchema = {
  type: "object" as const,
  properties: {},
  required: [] as string[],
};

export type CheckBalanceInput = Record<string, never>;

export type CheckBalanceOutput = {
  balance_usd: number;
  balance_usd_cents: number;
  auto_reload_enabled: boolean;
  message: string;
};

// ---------------------------------------------------------------------------
// get_payment_url
// ---------------------------------------------------------------------------

export const GetPaymentUrlInputSchema = {
  type: "object" as const,
  properties: {
    amount_usd: { type: "number" as const, description: "Amount to add to your Rhumb credit balance in USD (min $5, max $5000). Returns a checkout URL to complete payment." },
  },
  required: ["amount_usd"] as string[],
};

export type GetPaymentUrlInput = {
  amount_usd: number;
};

export type GetPaymentUrlOutput = {
  checkout_url: string;
  amount_usd: number;
  message: string;
};

// ---------------------------------------------------------------------------
// get_ledger
// ---------------------------------------------------------------------------

export const GetLedgerInputSchema = {
  type: "object" as const,
  properties: {
    limit: { type: "number" as const, description: "Number of entries (default 20, max 100). Most recent first." },
    event_type: { type: "string" as const, description: "Filter: 'debit' (execution charges), 'credit_added' (top-ups), 'auto_reload_triggered' (auto-refills). Omit for all types." },
  },
  required: [] as string[],
};

export type GetLedgerInput = {
  limit?: number;
  event_type?: string;
};

export type GetLedgerOutput = {
  entries: Array<{
    id: string;
    event_type: string;
    amount_usd_cents: number;
    balance_after_usd_cents: number;
    description: string;
    created_at: string;
  }>;
  total_count: number;
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
  check_credentials: CheckCredentialsInputSchema,
  budget: BudgetInputSchema,
  spend: SpendInputSchema,
  routing: RoutingInputSchema,
  check_balance: CheckBalanceInputSchema,
  get_payment_url: GetPaymentUrlInputSchema,
  get_ledger: GetLedgerInputSchema
} as const;

export const TOOL_NAMES = Object.keys(TOOL_SCHEMAS) as Array<keyof typeof TOOL_SCHEMAS>;

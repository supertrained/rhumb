/**
 * Rhumb MCP Server — API Client
 *
 * Lightweight client for the Rhumb REST API.
 * Follows the same parsing patterns as the web package adapters.
 */

// ---------------------------------------------------------------------------
// Shared result types (used by tool handlers)
// ---------------------------------------------------------------------------

export interface ServiceSearchItem {
  name: string;
  slug: string;
  aggregateScore: number | null;
  executionScore: number | null;
  accessScore: number | null;
  explanation: string;
}

export interface FailureModeItem {
  pattern: string;
  impact: string;
  frequency: string;
  workaround: string;
  tags: string[];
}

export interface ServiceScoreItem {
  slug: string;
  aggregateScore: number | null;
  executionScore: number | null;
  accessScore: number | null;
  confidence: number;
  tier: string;
  explanation: string;
  freshness: string;
  failureModes: FailureModeItem[];
  tags: string[];
}

// ---------------------------------------------------------------------------
// Billing result types
// ---------------------------------------------------------------------------

export interface BalanceResult {
  balance_usd: number;
  balance_usd_cents: number;
  auto_reload_enabled: boolean;
}

export interface CheckoutResult {
  checkout_url: string;
  session_id: string;
}

export interface LedgerEntry {
  id: string;
  event_type: string;
  amount_usd_cents: number;
  balance_after_usd_cents: number;
  description: string;
  created_at: string;
}

export interface LedgerResult {
  entries: LedgerEntry[];
  total_count: number;
}

export interface UsageTelemetryResult {
  agent_id: string;
  period_days: number;
  summary: {
    total_calls: number;
    successful_calls: number;
    failed_calls: number;
    total_cost_usd: number;
    avg_latency_ms: number;
    p50_latency_ms: number;
    p95_latency_ms: number;
  };
  by_capability: Array<{
    capability_id: string;
    calls: number;
    success_rate: number;
    avg_latency_ms: number;
    total_cost_usd: number;
    top_provider: string | null;
  }>;
  by_provider: Array<{
    provider: string;
    calls: number;
    success_rate: number;
    avg_latency_ms: number;
    total_cost_usd: number;
    error_rate: number;
    avg_upstream_latency_ms: number;
  }>;
  by_time: Array<{
    period: string;
    calls: number;
    success_rate: number;
    avg_latency_ms: number;
  }>;
}

// ---------------------------------------------------------------------------
// Client interface (for dependency injection / testing)
// ---------------------------------------------------------------------------

export interface CapabilitySearchItem {
  id: string;
  domain: string;
  action: string;
  description: string;
  inputHint: string;
  outcome: string;
  providerCount: number;
  topProvider: { slug: string; anScore: number | null; tierLabel: string } | null;
}

export interface CapabilityResolveProvider {
  serviceSlug: string;
  serviceName: string;
  anScore: number | null;
  costPerCall: number | null;
  freeTierCalls: number | null;
  authMethod: string;
  endpointPattern: string;
  recommendation: string;
  recommendationReason: string;
  credentialModes: string[];
  configured: boolean | null;
  availableForExecute: boolean | null;
  circuitState: string | null;
}

export interface CapabilityExecuteHint {
  preferredProvider: string;
  selectionReason: string | null;
  skippedProviderSlugs: string[];
  unavailableProviderSlugs: string[];
  notExecuteReadyProviderSlugs: string[];
  endpointPattern: string | null;
  estimatedCostUsd: number | null;
  authMethod: string;
  credentialModes: string[];
  configured: boolean;
  credentialModesUrl: string;
  preferredCredentialMode: string | null;
  fallbackProviders: string[];
  setupHint: string | null;
  setupUrl: string | null;
}

export interface CapabilityRecoveryHandoff {
  preferredProvider: string;
  selectionReason: string | null;
  endpointPattern: string | null;
  authMethod: string;
  credentialModes: string[];
  configured: boolean;
  credentialModesUrl: string;
  preferredCredentialMode: string | null;
  fallbackProviders: string[];
  setupHint: string | null;
  setupUrl: string | null;
}

export interface CapabilityRecoveryHint {
  reason: string;
  requestedCredentialMode: string | null;
  resolveUrl: string;
  credentialModesUrl: string;
  supportedProviderSlugs: string[];
  supportedCredentialModes: string[];
  unavailableProviderSlugs: string[];
  notExecuteReadyProviderSlugs: string[];
  alternateExecuteHint: CapabilityRecoveryHandoff | null;
  setupHandoff: CapabilityRecoveryHandoff | null;
}

export interface CapabilityResolveResult {
  capability: string;
  providers: CapabilityResolveProvider[];
  fallbackChain: string[];
  relatedBundles: string[];
  executeHint: CapabilityExecuteHint | null;
  recoveryHint: CapabilityRecoveryHint | null;
}

export interface CapabilityExecuteResult {
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
  /** Present when HTTP 402 is returned — contains x402 payment instructions */
  paymentRequired?: {
    x402Version: number;
    accepts: Array<Record<string, unknown>>;
    error: string;
    balanceRequired: number;
    balanceRequiredUsd: number;
  };
}

export interface CapabilityEstimateResult {
  capabilityId: string;
  provider: string;
  credentialMode: string;
  costEstimateUsd: number | null;
  circuitState: string;
  endpointPattern: string | null;
}

export interface RecipeSummaryItem {
  recipeId: string;
  name: string;
  version: string;
  category: string;
  stability: string;
  tier: string;
  stepCount: number;
  maxTotalCostUsd: number | null;
}

export interface RecipeDetailResult extends RecipeSummaryItem {
  definition: Record<string, unknown>;
  inputsSchema: Record<string, unknown>;
  outputsSchema: Record<string, unknown>;
  layer: number;
}

export interface RecipeExecutionResult {
  executionId: string;
  recipeId: string;
  status: string;
  totalCostUsd: number;
  totalDurationMs: number;
  startedAt: string | null;
  completedAt: string | null;
  error: string | null;
  receiptChainHash: string | null;
  deduplicated: boolean;
  layer: number;
  outputs: Record<string, unknown>;
  stepResults: Array<{
    stepId: string;
    capabilityId: string | null;
    status: string;
    outputs: Record<string, unknown>;
    costUsd: number;
    durationMs: number;
    receiptId: string | null;
    error: string | null;
    retriesUsed: number;
    providerUsed: string | null;
  }>;
}

export interface CeremonySummaryItem {
  service_slug: string;
  display_name: string;
  description: string;
  auth_type: string;
  difficulty: string;
  estimated_minutes: number;
  requires_human: boolean;
  documentation_url: string | null;
}

export interface CeremonyDetailItem extends CeremonySummaryItem {
  id: number;
  steps: Array<{ step: number; action: string; type: string }>;
  token_pattern: string | null;
  token_prefix: string | null;
  verify_endpoint: string | null;
  verify_method: string | null;
  verify_expected_status: number | null;
}

export interface ManagedCapabilityItem {
  capability_id: string;
  service_slug: string;
  description: string;
  daily_limit_per_agent: number | null;
  domain?: string;
  action?: string;
  capability_description?: string;
}

export interface RhumbApiClient {
  searchServices(query: string): Promise<ServiceSearchItem[]>;
  getServiceScore(slug: string): Promise<ServiceScoreItem | null>;
  discoverCapabilities(opts: { domain?: string; search?: string; limit?: number }): Promise<{ items: CapabilitySearchItem[]; total: number }>;
  resolveCapability(capabilityId: string): Promise<CapabilityResolveResult | null>;
  executeCapability(capabilityId: string, opts: {
    provider?: string;
    method?: string;
    path?: string;
    body?: Record<string, unknown>;
    params?: Record<string, string>;
    credentialMode?: string;
    idempotencyKey?: string;
    agentToken?: string;
    xPayment?: string;
    // v2 policy parameters — when any are set, routes through /v2/ for policy enforcement
    providerPreference?: string[];
    providerDeny?: string[];
    maxCostUsd?: number;
  }): Promise<CapabilityExecuteResult>;
  estimateCapability(capabilityId: string, opts?: {
    provider?: string;
    credentialMode?: string;
  }): Promise<CapabilityEstimateResult>;
  listRecipes?(opts?: {
    category?: string;
    stability?: string;
    limit?: number;
    offset?: number;
  }): Promise<{ items: RecipeSummaryItem[]; total: number; limit: number; offset: number }>;
  getRecipe?(recipeId: string): Promise<RecipeDetailResult | null>;
  executeRecipe?(recipeId: string, opts: {
    inputs?: Record<string, unknown>;
    credentialMode?: string;
    idempotencyKey?: string;
    policy?: Record<string, unknown>;
  }): Promise<RecipeExecutionResult>;
  listCeremonies(): Promise<CeremonySummaryItem[]>;
  getCeremony(serviceSlug: string): Promise<CeremonyDetailItem | null>;
  listManagedCapabilities(): Promise<ManagedCapabilityItem[]>;
  // Phase 4: Budget + Routing + Spend
  getBudget(): Promise<Record<string, unknown>>;
  setBudget(budgetUsd: number, period?: string, hardLimit?: boolean): Promise<Record<string, unknown>>;
  getSpend(period?: string): Promise<Record<string, unknown>>;
  getRoutingStrategy(): Promise<Record<string, unknown>>;
  setRoutingStrategy(strategy: string, qualityFloor?: number, maxCost?: number): Promise<Record<string, unknown>>;
  getUsageTelemetry(opts?: {
    days?: number;
    capability_id?: string;
    provider?: string;
  }): Promise<UsageTelemetryResult>;
  // Billing
  getBalance(): Promise<BalanceResult>;
  createCheckout(amount_usd: number): Promise<CheckoutResult>;
  getLedger(limit?: number, event_type?: string): Promise<LedgerResult>;
}

// ---------------------------------------------------------------------------
// Parse helpers (mirrors web/lib/adapters.ts patterns)
// ---------------------------------------------------------------------------

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null;
}

function asString(v: unknown): string | null {
  return typeof v === "string" && v.length > 0 ? v : null;
}

function asNumber(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

function asBoolean(v: unknown): boolean | null {
  return typeof v === "boolean" ? v : null;
}

function asStringArray(v: unknown): string[] {
  return Array.isArray(v)
    ? v.filter((item): item is string => typeof item === "string")
    : [];
}

function parseRecoveryHandoff(rawHint: Record<string, unknown>): CapabilityRecoveryHandoff {
  return {
    preferredProvider: asString(rawHint.preferred_provider) ?? "unknown",
    selectionReason: asString(rawHint.selection_reason),
    endpointPattern: asString(rawHint.endpoint_pattern),
    authMethod: asString(rawHint.auth_method) ?? "unknown",
    credentialModes: asStringArray(rawHint.credential_modes),
    configured: rawHint.configured === true,
    credentialModesUrl: asString(rawHint.credential_modes_url) ?? "",
    preferredCredentialMode: asString(rawHint.preferred_credential_mode),
    fallbackProviders: asStringArray(rawHint.fallback_providers),
    setupHint: asString(rawHint.setup_hint),
    setupUrl: asString(rawHint.setup_url)
  };
}

// ---------------------------------------------------------------------------
// Factory
// ---------------------------------------------------------------------------

export function createApiClient(baseUrl?: string): RhumbApiClient {
  const base = baseUrl ?? process.env.RHUMB_API_BASE_URL ?? "https://api.rhumb.dev/v1";
  const defaultHeaders = {
    "User-Agent": "rhumb-mcp/0.8.2",
    "X-Rhumb-Client": "mcp",
    "X-Agent-Name": "rhumb-mcp"
  };

  return {
    async searchServices(query: string): Promise<ServiceSearchItem[]> {
      const url = `${base}/search?q=${encodeURIComponent(query)}`;
      const res = await fetch(url, { headers: defaultHeaders });
      if (!res.ok) {
        throw new Error(`API returned ${res.status}`);
      }

      const payload: unknown = await res.json();
      if (!isRecord(payload) || !isRecord(payload.data)) {
        return [];
      }

      const items = Array.isArray(payload.data.results)
        ? payload.data.results
        : Array.isArray(payload.data.items)
          ? payload.data.items
          : [];

      return items
        .filter((item: unknown): item is Record<string, unknown> => isRecord(item))
        .map((item) => ({
          name: asString(item.name) ?? asString(item.slug) ?? asString(item.service_slug) ?? "unknown",
          slug: asString(item.service_slug) ?? asString(item.slug) ?? "unknown",
          aggregateScore: asNumber(item.an_score) ?? asNumber(item.aggregate_recommendation_score),
          executionScore: asNumber(item.execution_score),
          accessScore: asNumber(item.access_readiness_score),
          explanation: asString(item.explanation) ?? ""
        }))
        .filter((item) => item.slug !== "unknown");
    },

    async getServiceScore(slug: string): Promise<ServiceScoreItem | null> {
      const url = `${base}/services/${encodeURIComponent(slug)}/score`;
      const res = await fetch(url, { headers: defaultHeaders });

      if (!res.ok) {
        if (res.status === 404) return null;
        throw new Error(`API returned ${res.status}`);
      }

      const payload: unknown = await res.json();
      if (!isRecord(payload)) return null;

      const serviceSlug = asString(payload.service_slug);
      if (!serviceSlug) return null;

      const snapshot = isRecord(payload.dimension_snapshot)
        ? payload.dimension_snapshot
        : {};

      // Parse failure_modes array from API response
      const rawFailures = Array.isArray(payload.failure_modes)
        ? payload.failure_modes
        : [];

      const failureModes: FailureModeItem[] = rawFailures
        .filter((fm: unknown): fm is Record<string, unknown> => isRecord(fm))
        .map((fm) => ({
          pattern: asString(fm.pattern) ?? "unknown",
          impact: asString(fm.impact) ?? "unknown",
          frequency: asString(fm.frequency) ?? "unknown",
          workaround: asString(fm.workaround) ?? "none",
          tags: Array.isArray(fm.tags)
            ? (fm.tags as unknown[]).filter((t): t is string => typeof t === "string")
            : []
        }));

      // Collect unique tags from all failure modes
      const tagSet = new Set<string>();
      for (const fm of failureModes) {
        for (const tag of fm.tags) {
          tagSet.add(tag);
        }
      }

      return {
        slug: serviceSlug,
        aggregateScore: asNumber(payload.an_score) ?? asNumber(payload.aggregate_recommendation_score),
        executionScore: asNumber(payload.execution_score),
        accessScore: asNumber(payload.access_readiness_score),
        confidence: asNumber(payload.confidence) ?? 0,
        tier: asString(payload.tier) ?? "unknown",
        explanation: asString(payload.explanation) ?? "",
        freshness:
          asString(snapshot.probe_freshness) ??
          asString(snapshot.freshness) ??
          asString(snapshot.evidence_freshness) ??
          asString(payload.probe_freshness) ??
          "unknown",
        failureModes,
        tags: [...tagSet]
      };
    },

    async discoverCapabilities(opts: { domain?: string; search?: string; limit?: number }): Promise<{ items: CapabilitySearchItem[]; total: number }> {
      const params = new URLSearchParams();
      if (opts.domain) params.set("domain", opts.domain);
      if (opts.search) params.set("search", opts.search);
      if (opts.limit) params.set("limit", String(opts.limit));
      const qs = params.toString();
      const url = `${base}/capabilities${qs ? `?${qs}` : ""}`;

      const res = await fetch(url, { headers: defaultHeaders });
      if (!res.ok) {
        throw new Error(`API returned ${res.status}`);
      }

      const payload: unknown = await res.json();
      if (!isRecord(payload) || !isRecord(payload.data)) {
        return { items: [], total: 0 };
      }

      const rawItems = Array.isArray(payload.data.items) ? payload.data.items : [];
      const total = typeof payload.data.total === "number" ? payload.data.total : 0;

      const items: CapabilitySearchItem[] = rawItems
        .filter((item: unknown): item is Record<string, unknown> => isRecord(item))
        .map((item) => {
          const tp = isRecord(item.top_provider) ? item.top_provider : null;
          return {
            id: asString(item.id) ?? "unknown",
            domain: asString(item.domain) ?? "unknown",
            action: asString(item.action) ?? "unknown",
            description: asString(item.description) ?? "",
            inputHint: asString(item.input_hint) ?? "",
            outcome: asString(item.outcome) ?? "",
            providerCount: typeof item.provider_count === "number" ? item.provider_count : 0,
            topProvider: tp
              ? {
                  slug: asString(tp.slug) ?? "unknown",
                  anScore: asNumber(tp.an_score),
                  tierLabel: asString(tp.tier_label) ?? "Unknown"
                }
              : null
          };
        });

      return { items, total };
    },

    async resolveCapability(capabilityId: string): Promise<CapabilityResolveResult | null> {
      const url = `${base}/capabilities/${encodeURIComponent(capabilityId)}/resolve`;
      const res = await fetch(url, { headers: defaultHeaders });

      if (!res.ok) {
        if (res.status === 404) return null;
        throw new Error(`API returned ${res.status}`);
      }

      const payload: unknown = await res.json();
      if (!isRecord(payload) || !isRecord(payload.data)) return null;
      const data = payload.data;

      if (data.error) return null;

      const rawProviders = Array.isArray(data.providers) ? data.providers : [];
      const providers = rawProviders
        .filter((p: unknown): p is Record<string, unknown> => isRecord(p))
        .map((p) => ({
          serviceSlug: asString(p.service_slug) ?? "unknown",
          serviceName: asString(p.service_name) ?? asString(p.service_slug) ?? "unknown",
          anScore: asNumber(p.an_score),
          costPerCall: asNumber(p.cost_per_call),
          freeTierCalls: typeof p.free_tier_calls === "number" ? p.free_tier_calls : null,
          authMethod: asString(p.auth_method) ?? "unknown",
          endpointPattern: asString(p.endpoint_pattern) ?? "",
          recommendation: asString(p.recommendation) ?? "available",
          recommendationReason: asString(p.recommendation_reason) ?? "",
          credentialModes: asStringArray(p.credential_modes),
          configured: asBoolean(p.configured),
          availableForExecute: asBoolean(p.available_for_execute),
          circuitState: asString(p.circuit_state)
        }));

      const fallbackChain = Array.isArray(data.fallback_chain)
        ? (data.fallback_chain as unknown[]).filter((s): s is string => typeof s === "string")
        : [];

      const relatedBundles = Array.isArray(data.related_bundles)
        ? (data.related_bundles as unknown[]).filter((s): s is string => typeof s === "string")
        : [];

      const rawExecuteHint = isRecord(data.execute_hint) ? data.execute_hint : null;
      const executeHint = rawExecuteHint
        ? {
            preferredProvider: asString(rawExecuteHint.preferred_provider) ?? "unknown",
            selectionReason: asString(rawExecuteHint.selection_reason),
            skippedProviderSlugs: asStringArray(rawExecuteHint.skipped_provider_slugs),
            unavailableProviderSlugs: asStringArray(rawExecuteHint.unavailable_provider_slugs),
            notExecuteReadyProviderSlugs: asStringArray(rawExecuteHint.not_execute_ready_provider_slugs),
            endpointPattern: asString(rawExecuteHint.endpoint_pattern),
            estimatedCostUsd: asNumber(rawExecuteHint.estimated_cost_usd),
            authMethod: asString(rawExecuteHint.auth_method) ?? "unknown",
            credentialModes: asStringArray(rawExecuteHint.credential_modes),
            configured: rawExecuteHint.configured === true,
            credentialModesUrl: asString(rawExecuteHint.credential_modes_url) ?? "",
            preferredCredentialMode: asString(rawExecuteHint.preferred_credential_mode),
            fallbackProviders: asStringArray(rawExecuteHint.fallback_providers),
            setupHint: asString(rawExecuteHint.setup_hint),
            setupUrl: asString(rawExecuteHint.setup_url)
          }
        : null;

      const rawRecoveryHint = isRecord(data.recovery_hint) ? data.recovery_hint : null;
      const recoveryHint = rawRecoveryHint
        ? {
            reason: asString(rawRecoveryHint.reason) ?? "unknown",
            requestedCredentialMode: asString(rawRecoveryHint.requested_credential_mode),
            resolveUrl: asString(rawRecoveryHint.resolve_url) ?? "",
            credentialModesUrl: asString(rawRecoveryHint.credential_modes_url) ?? "",
            supportedProviderSlugs: asStringArray(rawRecoveryHint.supported_provider_slugs),
            supportedCredentialModes: asStringArray(rawRecoveryHint.supported_credential_modes),
            unavailableProviderSlugs: asStringArray(rawRecoveryHint.unavailable_provider_slugs),
            notExecuteReadyProviderSlugs: asStringArray(rawRecoveryHint.not_execute_ready_provider_slugs),
            alternateExecuteHint: isRecord(rawRecoveryHint.alternate_execute_hint)
              ? parseRecoveryHandoff(rawRecoveryHint.alternate_execute_hint)
              : null,
            setupHandoff: isRecord(rawRecoveryHint.setup_handoff)
              ? parseRecoveryHandoff(rawRecoveryHint.setup_handoff)
              : null
          }
        : null;

      return {
        capability: asString(data.capability) ?? capabilityId,
        providers,
        fallbackChain,
        relatedBundles,
        executeHint,
        recoveryHint
      };
    },

    async executeCapability(capabilityId: string, opts: {
      provider?: string;
      method?: string;
      path?: string;
      body?: Record<string, unknown>;
      params?: Record<string, string>;
      credentialMode?: string;
      idempotencyKey?: string;
      agentToken?: string;
      xPayment?: string;
      providerPreference?: string[];
      providerDeny?: string[];
      maxCostUsd?: number;
    }): Promise<CapabilityExecuteResult> {
      // Route through v2 when policy parameters are present
      const useV2 = !!(opts.providerPreference?.length || opts.providerDeny?.length || opts.maxCostUsd != null);
      const v2Base = base.replace(/\/v1$/, "/v2");
      const url = useV2
        ? `${v2Base}/capabilities/${encodeURIComponent(capabilityId)}/execute`
        : `${base}/capabilities/${encodeURIComponent(capabilityId)}/execute`;
      const apiKey = process.env.RHUMB_API_KEY;

      const reqHeaders: Record<string, string> = {
        ...defaultHeaders,
        "Content-Type": "application/json"
      };
      if (apiKey) {
        reqHeaders["X-Rhumb-Key"] = apiKey;
      }
      // Mode 3: pass agent token via header (NEVER in body or logs)
      if (opts.agentToken) {
        reqHeaders["X-Agent-Token"] = opts.agentToken;
      }
      // x402: pass payment proof for zero-signup execution
      if (opts.xPayment) {
        reqHeaders["X-Payment"] = opts.xPayment;
      }

      const reqBody: Record<string, unknown> = {
        interface: "mcp"
      };

      if (useV2) {
        // v2 request envelope
        if (opts.body) reqBody.parameters = opts.body;
        else if (opts.params) reqBody.parameters = opts.params;
        if (opts.credentialMode) reqBody.credential_mode = opts.credentialMode;
        if (opts.idempotencyKey) reqBody.idempotency_key = opts.idempotencyKey;
        // v2 policy block
        const policy: Record<string, unknown> = {};
        if (opts.provider) policy.pin = opts.provider;
        if (opts.providerPreference?.length) policy.provider_preference = opts.providerPreference;
        if (opts.providerDeny?.length) policy.provider_deny = opts.providerDeny;
        if (opts.maxCostUsd != null) policy.max_cost_usd = opts.maxCostUsd;
        if (Object.keys(policy).length > 0) reqBody.policy = policy;
      } else {
        // v1 request envelope
        if (opts.method) reqBody.method = opts.method;
        if (opts.path) reqBody.path = opts.path;
        if (opts.provider) reqBody.provider = opts.provider;
        if (opts.body) reqBody.body = opts.body;
        if (opts.params) reqBody.params = opts.params;
        if (opts.credentialMode) reqBody.credential_mode = opts.credentialMode;
        if (opts.idempotencyKey) reqBody.idempotency_key = opts.idempotencyKey;
      }

      const res = await fetch(url, {
        method: "POST",
        headers: reqHeaders,
        body: JSON.stringify(reqBody)
      });

      // x402: 402 Payment Required — return payment instructions instead of throwing
      if (res.status === 402) {
        const paymentBody: unknown = await res.json();
        if (isRecord(paymentBody)) {
          return {
            capabilityId,
            providerUsed: "none",
            credentialMode: "x402",
            upstreamStatus: 402,
            upstreamResponse: null,
            costEstimateUsd: typeof paymentBody.balanceRequiredUsd === "number"
              ? paymentBody.balanceRequiredUsd : null,
            latencyMs: null,
            fallbackAttempted: false,
            fallbackProvider: null,
            executionId: "payment_required",
            paymentRequired: {
              x402Version: typeof paymentBody.x402Version === "number" ? paymentBody.x402Version : 1,
              accepts: Array.isArray(paymentBody.accepts) ? paymentBody.accepts as Array<Record<string, unknown>> : [],
              error: asString(paymentBody.error) ?? "Payment required",
              balanceRequired: typeof paymentBody.balanceRequired === "number" ? paymentBody.balanceRequired : 0,
              balanceRequiredUsd: typeof paymentBody.balanceRequiredUsd === "number" ? paymentBody.balanceRequiredUsd : 0,
            }
          };
        }
      }

      if (!res.ok) {
        const errBody = await res.text();
        throw new Error(`Execute failed (${res.status}): ${errBody}`);
      }

      const payload: unknown = await res.json();
      if (!isRecord(payload) || !isRecord(payload.data)) {
        throw new Error("Invalid execute response");
      }

      const d = payload.data;
      return {
        capabilityId: asString(d.capability_id) ?? capabilityId,
        providerUsed: asString(d.provider_used) ?? "unknown",
        credentialMode: asString(d.credential_mode) ?? "auto",
        upstreamStatus: typeof d.upstream_status === "number" ? d.upstream_status : null,
        upstreamResponse: d.upstream_response ?? null,
        costEstimateUsd: asNumber(d.cost_estimate_usd),
        latencyMs: asNumber(d.latency_ms),
        fallbackAttempted: d.fallback_attempted === true,
        fallbackProvider: asString(d.fallback_provider),
        executionId: asString(d.execution_id) ?? "unknown",
        deduplicated: d.deduplicated === true
      };
    },

    async estimateCapability(capabilityId: string, opts?: {
      provider?: string;
      credentialMode?: string;
    }): Promise<CapabilityEstimateResult> {
      const params = new URLSearchParams();
      if (opts?.provider) params.set("provider", opts.provider);
      if (opts?.credentialMode) params.set("credential_mode", opts.credentialMode);
      const qs = params.toString();
      const url = `${base}/capabilities/${encodeURIComponent(capabilityId)}/execute/estimate${qs ? `?${qs}` : ""}`;

      const apiKey = process.env.RHUMB_API_KEY;
      const reqHeaders: Record<string, string> = { ...defaultHeaders };
      if (apiKey) {
        reqHeaders["X-Rhumb-Key"] = apiKey;
      }

      const res = await fetch(url, { headers: reqHeaders });

      if (!res.ok) {
        const errBody = await res.text();
        throw new Error(`Estimate failed (${res.status}): ${errBody}`);
      }

      const payload: unknown = await res.json();
      if (!isRecord(payload) || !isRecord(payload.data)) {
        throw new Error("Invalid estimate response");
      }

      const d = payload.data;
      return {
        capabilityId: asString(d.capability_id) ?? capabilityId,
        provider: asString(d.provider) ?? "unknown",
        credentialMode: asString(d.credential_mode) ?? "auto",
        costEstimateUsd: asNumber(d.cost_estimate_usd),
        circuitState: asString(d.circuit_state) ?? "unknown",
        endpointPattern: asString(d.endpoint_pattern)
      };
    },

    async listRecipes(opts?: {
      category?: string;
      stability?: string;
      limit?: number;
      offset?: number;
    }): Promise<{ items: RecipeSummaryItem[]; total: number; limit: number; offset: number }> {
      const params = new URLSearchParams();
      if (opts?.category) params.set("category", opts.category);
      if (opts?.stability) params.set("stability", opts.stability);
      if (opts?.limit != null) params.set("limit", String(opts.limit));
      if (opts?.offset != null) params.set("offset", String(opts.offset));
      const qs = params.toString();
      const v2Base = base.replace(/\/v1$/, "/v2");
      const url = `${v2Base}/recipes${qs ? `?${qs}` : ""}`;

      const res = await fetch(url, { headers: defaultHeaders });
      if (!res.ok) {
        throw new Error(`List recipes failed (${res.status})`);
      }

      const payload: unknown = await res.json();
      if (!isRecord(payload) || !isRecord(payload.data)) {
        return { items: [], total: 0, limit: opts?.limit ?? 50, offset: opts?.offset ?? 0 };
      }

      const data = payload.data;
      const rawItems = Array.isArray(data.recipes) ? data.recipes : [];
      const items: RecipeSummaryItem[] = rawItems
        .filter((item: unknown): item is Record<string, unknown> => isRecord(item))
        .map((item) => ({
          recipeId: asString(item.recipe_id) ?? "unknown",
          name: asString(item.name) ?? asString(item.recipe_id) ?? "unknown",
          version: asString(item.version) ?? "1.0.0",
          category: asString(item.category) ?? "",
          stability: asString(item.stability) ?? "beta",
          tier: asString(item.tier) ?? "premium",
          stepCount: asNumber(item.step_count) ?? 0,
          maxTotalCostUsd: asNumber(item.max_total_cost_usd),
        }))
        .filter((item) => item.recipeId !== "unknown");

      return {
        items,
        total: asNumber(data.count) ?? items.length,
        limit: asNumber(data.limit) ?? (opts?.limit ?? 50),
        offset: asNumber(data.offset) ?? (opts?.offset ?? 0),
      };
    },

    async getRecipe(recipeId: string): Promise<RecipeDetailResult | null> {
      const v2Base = base.replace(/\/v1$/, "/v2");
      const url = `${v2Base}/recipes/${encodeURIComponent(recipeId)}`;
      const res = await fetch(url, { headers: defaultHeaders });
      if (!res.ok) {
        if (res.status === 404) return null;
        throw new Error(`Get recipe failed (${res.status})`);
      }

      const payload: unknown = await res.json();
      if (!isRecord(payload) || !isRecord(payload.data)) return null;
      const data = payload.data;
      return {
        recipeId: asString(data.recipe_id) ?? recipeId,
        name: asString(data.name) ?? recipeId,
        version: asString(data.version) ?? "1.0.0",
        category: asString(data.category) ?? "",
        stability: asString(data.stability) ?? "beta",
        tier: asString(data.tier) ?? "premium",
        stepCount: asNumber(data.step_count) ?? 0,
        maxTotalCostUsd: asNumber(data.max_total_cost_usd),
        definition: isRecord(data.definition) ? data.definition : {},
        inputsSchema: isRecord(data.inputs_schema) ? data.inputs_schema : {},
        outputsSchema: isRecord(data.outputs_schema) ? data.outputs_schema : {},
        layer: asNumber(data.layer) ?? 3,
      };
    },

    async executeRecipe(recipeId: string, opts: {
      inputs?: Record<string, unknown>;
      credentialMode?: string;
      idempotencyKey?: string;
      policy?: Record<string, unknown>;
    }): Promise<RecipeExecutionResult> {
      const v2Base = base.replace(/\/v1$/, "/v2");
      const url = `${v2Base}/recipes/${encodeURIComponent(recipeId)}/execute`;
      const apiKey = process.env.RHUMB_API_KEY;
      const reqHeaders: Record<string, string> = {
        ...defaultHeaders,
        "Content-Type": "application/json",
      };
      if (apiKey) reqHeaders["X-Rhumb-Key"] = apiKey;

      const reqBody: Record<string, unknown> = {
        inputs: opts.inputs ?? {},
        credential_mode: opts.credentialMode ?? "rhumb_managed",
        interface: "mcp",
      };
      if (opts.idempotencyKey) reqBody.idempotency_key = opts.idempotencyKey;
      if (opts.policy) reqBody.policy = opts.policy;

      const res = await fetch(url, {
        method: "POST",
        headers: reqHeaders,
        body: JSON.stringify(reqBody),
      });
      if (!res.ok) {
        const errBody = await res.text();
        throw new Error(`Recipe execute failed (${res.status}): ${errBody}`);
      }

      const payload: unknown = await res.json();
      if (!isRecord(payload) || !isRecord(payload.data)) {
        throw new Error("Invalid recipe execute response");
      }
      const data = payload.data;
      const rawSteps = Array.isArray(data.step_results) ? data.step_results : [];
      return {
        executionId: asString(data.execution_id) ?? "unknown",
        recipeId: asString(data.recipe_id) ?? recipeId,
        status: asString(data.status) ?? "unknown",
        totalCostUsd: asNumber(data.total_cost_usd) ?? 0,
        totalDurationMs: asNumber(data.total_duration_ms) ?? 0,
        startedAt: asString(data.started_at),
        completedAt: asString(data.completed_at),
        error: asString(data.error),
        receiptChainHash: asString(data.receipt_chain_hash),
        deduplicated: data.deduplicated === true,
        layer: asNumber(data.layer) ?? 3,
        outputs: isRecord(data.outputs) ? data.outputs : {},
        stepResults: rawSteps
          .filter((step: unknown): step is Record<string, unknown> => isRecord(step))
          .map((step) => ({
            stepId: asString(step.step_id) ?? "unknown",
            capabilityId: asString(step.capability_id),
            status: asString(step.status) ?? "unknown",
            outputs: isRecord(step.outputs) ? step.outputs : {},
            costUsd: asNumber(step.cost_usd) ?? 0,
            durationMs: asNumber(step.duration_ms) ?? 0,
            receiptId: asString(step.receipt_id),
            error: asString(step.error),
            retriesUsed: asNumber(step.retries_used) ?? 0,
            providerUsed: asString(step.provider_used),
          })),
      };
    },

    async listCeremonies(): Promise<CeremonySummaryItem[]> {
      const url = `${base}/services/ceremonies`;
      const res = await fetch(url, { headers: defaultHeaders });
      if (!res.ok) return [];

      const payload: unknown = await res.json();
      if (!isRecord(payload) || !isRecord(payload.data)) return [];

      return Array.isArray(payload.data.ceremonies) ? payload.data.ceremonies : [];
    },

    async getCeremony(serviceSlug: string): Promise<CeremonyDetailItem | null> {
      const url = `${base}/services/${encodeURIComponent(serviceSlug)}/ceremony`;
      const res = await fetch(url, { headers: defaultHeaders });
      if (!res.ok) return null;

      const payload: unknown = await res.json();
      if (!isRecord(payload) || !isRecord(payload.data)) return null;
      if (payload.error) return null;

      return payload.data as unknown as CeremonyDetailItem;
    },

    async listManagedCapabilities(): Promise<ManagedCapabilityItem[]> {
      const url = `${base}/capabilities/rhumb-managed`;
      const res = await fetch(url, { headers: defaultHeaders });
      if (!res.ok) return [];

      const payload: unknown = await res.json();
      if (!isRecord(payload) || !isRecord(payload.data)) return [];

      return Array.isArray(payload.data.managed_capabilities)
        ? payload.data.managed_capabilities
        : [];
    },

    // -- Phase 4: Budget + Routing + Spend --------------------------------

    async getBudget(): Promise<Record<string, unknown>> {
      const url = `${base}/agent/budget`;
      const apiKey = process.env.RHUMB_API_KEY;
      const reqHeaders: Record<string, string> = { ...defaultHeaders };
      if (apiKey) reqHeaders["X-Rhumb-Key"] = apiKey;
      const res = await fetch(url, { headers: reqHeaders });
      if (!res.ok) return { unlimited: true };
      return (await res.json()) as Record<string, unknown>;
    },

    async setBudget(budgetUsd: number, period?: string, hardLimit?: boolean): Promise<Record<string, unknown>> {
      const url = `${base}/agent/budget`;
      const apiKey = process.env.RHUMB_API_KEY;
      const body: Record<string, unknown> = { budget_usd: budgetUsd };
      if (period) body.period = period;
      if (hardLimit !== undefined) body.hard_limit = hardLimit;

      const reqHeaders: Record<string, string> = { ...defaultHeaders, "Content-Type": "application/json" };
      if (apiKey) reqHeaders["X-Rhumb-Key"] = apiKey;

      const res = await fetch(url, {
        method: "PUT",
        headers: reqHeaders,
        body: JSON.stringify(body),
      });
      if (!res.ok) return { error: `Failed to set budget: ${res.status}` };
      return (await res.json()) as Record<string, unknown>;
    },

    async getSpend(period?: string): Promise<Record<string, unknown>> {
      const params = period ? `?period=${encodeURIComponent(period)}` : "";
      const url = `${base}/agent/spend${params}`;
      const apiKey = process.env.RHUMB_API_KEY;
      const reqHeaders: Record<string, string> = { ...defaultHeaders };
      if (apiKey) reqHeaders["X-Rhumb-Key"] = apiKey;
      const res = await fetch(url, { headers: reqHeaders });
      if (!res.ok) return { total_spend_usd: 0, total_executions: 0, by_capability: [], by_provider: [] };
      return (await res.json()) as Record<string, unknown>;
    },

    async getRoutingStrategy(): Promise<Record<string, unknown>> {
      const url = `${base}/agent/routing-strategy`;
      const apiKey = process.env.RHUMB_API_KEY;
      const reqHeaders: Record<string, string> = { ...defaultHeaders };
      if (apiKey) reqHeaders["X-Rhumb-Key"] = apiKey;
      const res = await fetch(url, { headers: reqHeaders });
      if (!res.ok) return { strategy: "balanced", quality_floor: 6.0 };
      return (await res.json()) as Record<string, unknown>;
    },

    async setRoutingStrategy(strategy: string, qualityFloor?: number, maxCost?: number): Promise<Record<string, unknown>> {
      const url = `${base}/agent/routing-strategy`;
      const apiKey = process.env.RHUMB_API_KEY;
      const body: Record<string, unknown> = { strategy };
      if (qualityFloor !== undefined) body.quality_floor = qualityFloor;
      if (maxCost !== undefined) body.max_cost_per_call_usd = maxCost;

      const reqHeaders: Record<string, string> = { ...defaultHeaders, "Content-Type": "application/json" };
      if (apiKey) reqHeaders["X-Rhumb-Key"] = apiKey;

      const res = await fetch(url, {
        method: "PUT",
        headers: reqHeaders,
        body: JSON.stringify(body),
      });
      if (!res.ok) return { error: `Failed to set strategy: ${res.status}` };
      return (await res.json()) as Record<string, unknown>;
    },

    async getUsageTelemetry(opts?: {
      days?: number;
      capability_id?: string;
      provider?: string;
    }): Promise<UsageTelemetryResult> {
      const params = new URLSearchParams();
      if (opts?.days) params.set("days", String(opts.days));
      if (opts?.capability_id) params.set("capability_id", opts.capability_id);
      if (opts?.provider) params.set("provider", opts.provider);

      const qs = params.toString();
      const url = `${base}/telemetry/usage${qs ? `?${qs}` : ""}`;
      const apiKey = process.env.RHUMB_API_KEY;
      if (!apiKey) {
        throw new Error("RHUMB_API_KEY is required for usage telemetry");
      }

      const reqHeaders: Record<string, string> = {
        ...defaultHeaders,
        "X-Rhumb-Key": apiKey
      };
      const res = await fetch(url, { headers: reqHeaders });
      if (!res.ok) {
        throw new Error(`Usage telemetry fetch failed: ${res.status}`);
      }

      const payload: unknown = await res.json();
      if (!isRecord(payload) || !isRecord(payload.data)) {
        throw new Error("Usage telemetry response was malformed");
      }

      return payload.data as unknown as UsageTelemetryResult;
    },

    // -- Billing ----------------------------------------------------------

    async getBalance(): Promise<BalanceResult> {
      const url = `${base}/billing/balance`;
      const apiKey = process.env.RHUMB_API_KEY;
      const reqHeaders: Record<string, string> = { ...defaultHeaders };
      if (apiKey) reqHeaders["X-Rhumb-Key"] = apiKey;
      const res = await fetch(url, { headers: reqHeaders });
      if (!res.ok) throw new Error(`Balance check failed: ${res.status}`);
      return (await res.json()) as BalanceResult;
    },

    async createCheckout(amount_usd: number): Promise<CheckoutResult> {
      const url = `${base}/billing/checkout`;
      const apiKey = process.env.RHUMB_API_KEY;
      const reqHeaders: Record<string, string> = { ...defaultHeaders, "Content-Type": "application/json" };
      if (apiKey) reqHeaders["X-Rhumb-Key"] = apiKey;

      const res = await fetch(url, {
        method: "POST",
        headers: reqHeaders,
        body: JSON.stringify({ amount_usd }),
      });
      if (!res.ok) throw new Error(`Checkout failed: ${res.status}`);
      return (await res.json()) as CheckoutResult;
    },

    async getLedger(limit?: number, event_type?: string): Promise<LedgerResult> {
      const params = new URLSearchParams();
      if (limit) params.set("limit", String(limit));
      if (event_type) params.set("event_type", event_type);
      const qs = params.toString();
      const url = `${base}/billing/ledger${qs ? `?${qs}` : ""}`;
      const apiKey = process.env.RHUMB_API_KEY;
      const reqHeaders: Record<string, string> = { ...defaultHeaders };
      if (apiKey) reqHeaders["X-Rhumb-Key"] = apiKey;
      const res = await fetch(url, { headers: reqHeaders });
      if (!res.ok) throw new Error(`Ledger fetch failed: ${res.status}`);
      return (await res.json()) as LedgerResult;
    }
  };
}

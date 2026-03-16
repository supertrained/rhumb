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

export interface CapabilityResolveResult {
  capability: string;
  providers: Array<{
    serviceSlug: string;
    serviceName: string;
    anScore: number | null;
    costPerCall: number | null;
    freeTierCalls: number | null;
    authMethod: string;
    endpointPattern: string;
    recommendation: string;
    recommendationReason: string;
  }>;
  fallbackChain: string[];
  relatedBundles: string[];
}

export interface RhumbApiClient {
  searchServices(query: string): Promise<ServiceSearchItem[]>;
  getServiceScore(slug: string): Promise<ServiceScoreItem | null>;
  discoverCapabilities(opts: { domain?: string; search?: string; limit?: number }): Promise<{ items: CapabilitySearchItem[]; total: number }>;
  resolveCapability(capabilityId: string): Promise<CapabilityResolveResult | null>;
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

// ---------------------------------------------------------------------------
// Factory
// ---------------------------------------------------------------------------

export function createApiClient(baseUrl?: string): RhumbApiClient {
  const base = baseUrl ?? process.env.RHUMB_API_BASE_URL ?? "http://localhost:8000/v1";
  const defaultHeaders = {
    "User-Agent": "rhumb-mcp/0.0.1",
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
          aggregateScore: asNumber(item.aggregate_recommendation_score),
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
        aggregateScore: asNumber(payload.aggregate_recommendation_score),
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
          recommendationReason: asString(p.recommendation_reason) ?? ""
        }));

      const fallbackChain = Array.isArray(data.fallback_chain)
        ? (data.fallback_chain as unknown[]).filter((s): s is string => typeof s === "string")
        : [];

      const relatedBundles = Array.isArray(data.related_bundles)
        ? (data.related_bundles as unknown[]).filter((s): s is string => typeof s === "string")
        : [];

      return {
        capability: asString(data.capability) ?? capabilityId,
        providers,
        fallbackChain,
        relatedBundles
      };
    }
  };
}

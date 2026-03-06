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

export interface ServiceScoreItem {
  slug: string;
  aggregateScore: number | null;
  executionScore: number | null;
  accessScore: number | null;
  confidence: number;
  tier: string;
  explanation: string;
  freshness: string;
}

// ---------------------------------------------------------------------------
// Client interface (for dependency injection / testing)
// ---------------------------------------------------------------------------

export interface RhumbApiClient {
  searchServices(query: string): Promise<ServiceSearchItem[]>;
  getServiceScore(slug: string): Promise<ServiceScoreItem | null>;
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

  return {
    async searchServices(query: string): Promise<ServiceSearchItem[]> {
      const url = `${base}/services?query=${encodeURIComponent(query)}`;
      const res = await fetch(url);
      if (!res.ok) {
        throw new Error(`API returned ${res.status}`);
      }

      const payload: unknown = await res.json();
      if (!isRecord(payload) || !isRecord(payload.data)) {
        return [];
      }

      const items = Array.isArray(payload.data.items) ? payload.data.items : [];

      return items
        .filter((item: unknown): item is Record<string, unknown> => isRecord(item))
        .map((item) => ({
          name: asString(item.name) ?? asString(item.slug) ?? "unknown",
          slug: asString(item.slug) ?? "unknown",
          aggregateScore: asNumber(item.aggregate_recommendation_score),
          executionScore: asNumber(item.execution_score),
          accessScore: asNumber(item.access_readiness_score),
          explanation: asString(item.explanation) ?? ""
        }))
        .filter((item) => item.slug !== "unknown");
    },

    async getServiceScore(slug: string): Promise<ServiceScoreItem | null> {
      const url = `${base}/services/${encodeURIComponent(slug)}/score`;
      const res = await fetch(url);

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
          "unknown"
      };
    }
  };
}

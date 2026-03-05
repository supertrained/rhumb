import type {
  LeaderboardItem,
  LeaderboardViewModel,
  Service,
  ServiceAlternative,
  ServiceFailureMode,
  ServiceScoreViewModel
} from "./types";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function asString(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

function asNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function asItems(value: unknown): Record<string, unknown>[] {
  if (!Array.isArray(value)) {
    return [];
  }

  return value.filter((item): item is Record<string, unknown> => isRecord(item));
}

export function parseServicesResponse(payload: unknown): Service[] {
  if (!isRecord(payload) || !isRecord(payload.data)) {
    return [];
  }

  return asItems(payload.data.items)
    .map((item) => {
      const slug = asString(item.slug);
      const name = asString(item.name);
      const category = asString(item.category);
      if (!slug || !name || !category) {
        return null;
      }

      const description = asString(item.description);
      return {
        slug,
        name,
        category,
        ...(description ? { description } : {})
      };
    })
    .filter((service): service is Service => service !== null);
}

function parseLeaderboardItem(item: Record<string, unknown>): LeaderboardItem | null {
  const serviceSlug = asString(item.service_slug);
  if (!serviceSlug) {
    return null;
  }

  return {
    serviceSlug,
    name: asString(item.name) ?? serviceSlug,
    aggregateRecommendationScore: asNumber(item.aggregate_recommendation_score),
    executionScore: asNumber(item.execution_score),
    accessReadinessScore: asNumber(item.access_readiness_score),
    freshness: asString(item.probe_freshness) ?? asString(item.freshness),
    calculatedAt: asString(item.calculated_at),
    tier: asString(item.tier),
    confidence: asNumber(item.confidence)
  };
}

export function parseLeaderboardResponse(payload: unknown): LeaderboardViewModel {
  if (!isRecord(payload) || !isRecord(payload.data)) {
    return { category: "unknown", items: [], error: "Invalid leaderboard payload" };
  }

  const category = asString(payload.data.category) ?? "unknown";
  const items = asItems(payload.data.items)
    .map((item) => parseLeaderboardItem(item))
    .filter((item): item is LeaderboardItem => item !== null);

  return { category, items, error: null };
}

function parseFailureMode(item: Record<string, unknown>): ServiceFailureMode | null {
  const summary = asString(item.summary);
  if (!summary) {
    return null;
  }

  return {
    id: asString(item.id),
    summary
  };
}

function parseAlternative(item: Record<string, unknown>): ServiceAlternative | null {
  const serviceSlug = asString(item.service) ?? asString(item.service_slug);
  if (!serviceSlug) {
    return null;
  }

  return {
    serviceSlug,
    score: asNumber(item.score)
  };
}

function parseEvidenceFreshness(snapshot: Record<string, unknown>): string | null {
  return (
    asString(snapshot.probe_freshness) ??
    asString(snapshot.freshness) ??
    asString(snapshot.evidence_freshness)
  );
}

export function parseServiceScoreResponse(payload: unknown): ServiceScoreViewModel | null {
  if (!isRecord(payload)) {
    return null;
  }

  const serviceSlug = asString(payload.service_slug);
  if (!serviceSlug) {
    return null;
  }

  const snapshot = isRecord(payload.dimension_snapshot) ? payload.dimension_snapshot : {};
  const activeFailures = asItems(snapshot.active_failures)
    .map((item) => parseFailureMode(item))
    .filter((item): item is ServiceFailureMode => item !== null);
  const alternatives = asItems(snapshot.alternatives)
    .map((item) => parseAlternative(item))
    .filter((item): item is ServiceAlternative => item !== null);

  return {
    serviceSlug,
    aggregateRecommendationScore: asNumber(payload.aggregate_recommendation_score),
    executionScore: asNumber(payload.execution_score),
    accessReadinessScore: asNumber(payload.access_readiness_score),
    confidence: asNumber(payload.confidence),
    tier: asString(payload.tier),
    tierLabel: asString(payload.tier_label),
    explanation: asString(payload.explanation),
    calculatedAt: asString(payload.calculated_at),
    evidenceFreshness: parseEvidenceFreshness(snapshot) ?? asString(payload.probe_freshness),
    activeFailures,
    alternatives
  };
}

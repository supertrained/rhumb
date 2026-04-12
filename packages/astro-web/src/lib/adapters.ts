import type {
  EvidenceTier,
  LeaderboardItem,
  LeaderboardViewModel,
  ReviewTrustSource,
  Service,
  ServiceAlternative,
  ServiceFailureMode,
  ServiceReview,
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

function parseDashboardCounts(value: unknown): { key: string; count: number }[] {
  return asItems(value)
    .map((item) => {
      const key = asString(item.key);
      const count = asNumber(item.count);
      if (!key || count === null) {
        return null;
      }
      return { key, count };
    })
    .filter((item): item is { key: string; count: number } => item !== null);
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
    confidence: asNumber(item.confidence),
    p1Score: asNumber(item.p1_score),
    g1Score: asNumber(item.g1_score),
    w1Score: asNumber(item.w1_score),
    evidenceTier: (asString(item.evidence_tier) as EvidenceTier) ?? "assessed",
    evidenceCount: asNumber(item.evidence_count) ?? 0,
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

function parseReviewTrustSource(value: unknown, trustLabel: unknown): ReviewTrustSource {
  if (
    value === "docs_derived"
    || value === "tester_generated"
    || value === "runtime_verified"
  ) {
    return value;
  }

  const label = asString(trustLabel);
  if (label?.includes("Docs-derived")) {
    return "docs_derived";
  }
  if (label?.includes("Tester-generated")) {
    return "tester_generated";
  }
  if (label?.includes("Runtime-verified")) {
    return "runtime_verified";
  }

  return "unknown";
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
    alternatives,
    p1Score: asNumber(payload.p1_score),
    g1Score: asNumber(payload.g1_score),
    w1Score: asNumber(payload.w1_score),
    p1Rationale: asString(payload.p1_rationale),
    g1Rationale: asString(payload.g1_rationale),
    w1Rationale: asString(payload.w1_rationale),
    autonomyTier: asString(payload.autonomy_tier),
    baseUrl: asString(payload.base_url),
    docsUrl: asString(payload.docs_url),
    openapiUrl: asString(payload.openapi_url),
    mcpServerUrl: asString(payload.mcp_server_url),
    evidenceTier: (asString(payload.evidence_tier) as EvidenceTier) ?? "assessed",
    evidenceTierLabel: asString(payload.evidence_tier_label) ?? "Assessed",
    evidenceCount: asNumber(payload.evidence_count) ?? 0,
    lastEvaluated: asString(payload.last_evaluated) ?? asString(payload.calculated_at),
  };
}

export function parseServiceReviewsResponse(payload: unknown): ServiceReview[] {
  if (!isRecord(payload)) {
    return [];
  }

  return asItems(payload.reviews)
    .map((item) => {
      const id = asString(item.id);
      if (!id) {
        return null;
      }

      return {
        id,
        headline: asString(item.headline),
        summary: asString(item.summary),
        reviewerLabel: asString(item.reviewer_label),
        reviewedAt: asString(item.reviewed_at),
        confidence: asNumber(item.confidence),
        evidenceCount: asNumber(item.evidence_count) ?? 0,
        trustSource: parseReviewTrustSource(item.highest_trust_source, item.trust_label),
      };
    })
    .filter((item): item is ServiceReview => item !== null);
}

export function parseLaunchDashboardResponse(payload: unknown) {
  if (!isRecord(payload) || !isRecord(payload.data)) {
    return null;
  }

  const data = payload.data;
  const coverage = isRecord(data.coverage) ? data.coverage : {};
  const queries = isRecord(data.queries) ? data.queries : {};
  const clicks = isRecord(data.clicks) ? data.clicks : {};
  const funnel = isRecord(data.funnel) ? data.funnel : {};
  const executions = isRecord(data.executions) ? data.executions : {};
  const disputeClicks = isRecord(clicks.dispute_clicks) ? clicks.dispute_clicks : {};
  const callerCohorts = isRecord(executions.caller_cohorts) ? executions.caller_cohorts : {};
  const managedPath = isRecord(executions.managed_path) ? executions.managed_path : {};

  const parseExecutionCohort = (row: unknown) => {
    if (!isRecord(row)) {
      return { attempts: 0, successful: 0, failed: 0, successRate: null };
    }

    return {
      attempts: asNumber(row.attempts) ?? 0,
      successful: asNumber(row.successful) ?? 0,
      failed: asNumber(row.failed) ?? 0,
      successRate: asNumber(row.success_rate),
    };
  };

  const providerCtr = asItems(clicks.provider_ctr).map((row) => ({
    service_slug: asString(row.service_slug) ?? "unknown",
    clicks: asNumber(row.clicks) ?? 0,
    views: asNumber(row.views) ?? 0,
    ctr: asNumber(row.ctr),
  }));

  const parseFunnelTransition = (row: unknown) => {
    if (!isRecord(row)) {
      return null;
    }

    return {
      fromStage: asString(row.from_stage) ?? "unknown",
      toStage: asString(row.to_stage) ?? "unknown",
      fromCount: asNumber(row.from_count) ?? 0,
      toCount: asNumber(row.to_count) ?? 0,
      progressedCount: asNumber(row.progressed_count) ?? 0,
      dropoffCount: asNumber(row.dropoff_count) ?? 0,
      dropoffRate: asNumber(row.dropoff_rate),
      conversionRate: asNumber(row.conversion_rate),
      overflowCount: asNumber(row.overflow_count) ?? 0,
    };
  };

  const successTrend = asItems(executions.success_trend).map((row) => ({
    period: asString(row.period) ?? "unknown",
    total: asNumber(row.total) ?? 0,
    successful: asNumber(row.successful) ?? 0,
    failed: asNumber(row.failed) ?? 0,
    successRate: asNumber(row.success_rate),
  }));
  const stageTransitions = asItems(funnel.stage_transitions)
    .map(parseFunnelTransition)
    .filter((row): row is NonNullable<ReturnType<typeof parseFunnelTransition>> => row !== null);
  const biggestDropoff = parseFunnelTransition(funnel.biggest_dropoff);

  const window = asString(data.window);
  const startAt = asString(data.start_at);
  const generatedAt = asString(data.generated_at);

  if (
    (window !== "24h" && window !== "7d" && window !== "launch")
    || !startAt
    || !generatedAt
  ) {
    return null;
  }

  const parsedWindow: "24h" | "7d" | "launch" = window;

  return {
    window: parsedWindow,
    startAt,
    generatedAt,
    coverage: {
      publicServiceCount: asNumber(coverage.public_service_count) ?? 0,
    },
    queries: {
      total: asNumber(queries.total) ?? 0,
      machineTotal: asNumber(queries.machine_total) ?? 0,
      bySource: parseDashboardCounts(queries.by_source),
      topQueryTypes: parseDashboardCounts(queries.top_query_types),
      topServices: parseDashboardCounts(queries.top_services),
      topSearches: parseDashboardCounts(queries.top_searches),
      uniqueClients: asNumber(queries.unique_clients) ?? 0,
      repeatClients: asNumber(queries.repeat_clients) ?? 0,
      repeatClientRate: asNumber(queries.repeat_client_rate),
      latestActivityAt: asString(queries.latest_activity_at),
    },
    clicks: {
      total: asNumber(clicks.total) ?? 0,
      providerClicks: asNumber(clicks.provider_clicks) ?? 0,
      topProviderDomains: parseDashboardCounts(clicks.top_provider_domains),
      topSourceSurfaces: parseDashboardCounts(clicks.top_source_surfaces),
      providerCtr,
      disputeClicks: {
        email: asNumber(disputeClicks.email) ?? 0,
        github: asNumber(disputeClicks.github) ?? 0,
        contact: asNumber(disputeClicks.contact) ?? 0,
      },
      latestActivityAt: asString(clicks.latest_activity_at),
    },
    funnel: {
      queries: asNumber(funnel.queries) ?? 0,
      serviceViews: asNumber(funnel.service_views) ?? 0,
      providerClicks: asNumber(funnel.provider_clicks) ?? 0,
      executeAttempts: asNumber(funnel.execute_attempts) ?? 0,
      successfulExecutes: asNumber(funnel.successful_executes) ?? 0,
      stageTransitions,
      biggestDropoff,
    },
    executions: {
      total: asNumber(executions.total) ?? 0,
      successful: asNumber(executions.successful) ?? 0,
      failed: asNumber(executions.failed) ?? 0,
      uniqueCallers: asNumber(executions.unique_callers) ?? 0,
      firstTimeCallers: asNumber(executions.first_time_callers) ?? 0,
      repeatCallers: asNumber(executions.repeat_callers) ?? 0,
      repeatCallerRate: asNumber(executions.repeat_caller_rate),
      callerCohorts: {
        firstTime: parseExecutionCohort(callerCohorts.first_time),
        repeat: parseExecutionCohort(callerCohorts.repeat),
        unattributed: parseExecutionCohort(callerCohorts.unattributed),
      },
      credentialModes: parseDashboardCounts(executions.credential_modes),
      firstSuccessModes: parseDashboardCounts(executions.first_success_modes),
      managedPath: {
        attempts: asNumber(managedPath.attempts) ?? 0,
        successful: asNumber(managedPath.successful) ?? 0,
        failed: asNumber(managedPath.failed) ?? 0,
        successRate: asNumber(managedPath.success_rate),
        firstSuccessCallers: asNumber(managedPath.first_success_callers) ?? 0,
        firstSuccessShare: asNumber(managedPath.first_success_share),
      },
      topInterfaces: parseDashboardCounts(executions.top_interfaces),
      successRate: asNumber(executions.success_rate),
      topCapabilities: parseDashboardCounts(executions.top_capabilities),
      successTrend,
      latestActivityAt: asString(executions.latest_activity_at),
    },
  };
}

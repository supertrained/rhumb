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

function firstString(...values: unknown[]): string | null {
  for (const value of values) {
    const parsed = asString(value);
    if (parsed !== null) return parsed;
  }
  return null;
}

function firstNumber(...values: unknown[]): number | null {
  for (const value of values) {
    const parsed = asNumber(value);
    if (parsed !== null) return parsed;
  }
  return null;
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
  const serviceSlug = firstString(item.service_slug, item.slug);
  if (!serviceSlug) {
    return null;
  }

  return {
    serviceSlug,
    name: asString(item.name) ?? serviceSlug,
    aggregateRecommendationScore: firstNumber(item.aggregate_recommendation_score, item.an_score, item.score),
    executionScore: asNumber(item.execution_score),
    accessReadinessScore: firstNumber(item.access_readiness_score, item.access_score),
    freshness: firstString(item.probe_freshness, item.freshness),
    calculatedAt: asString(item.calculated_at),
    tier: asString(item.tier),
    confidence: asNumber(item.confidence),
    p1Score: firstNumber(item.p1_score, item.payment_autonomy),
    g1Score: firstNumber(item.g1_score, item.governance_readiness),
    w1Score: firstNumber(item.w1_score, item.web_accessibility),
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
  const summary = firstString(item.summary, item.pattern, item.title);
  if (!summary) {
    return null;
  }

  return {
    id: asString(item.id),
    summary,
    description: firstString(item.description, item.impact),
    severity: asString(item.severity),
    frequency: asString(item.frequency),
    agentImpact: asString(item.agent_impact) ?? asString(item.impact),
    workaround: asString(item.workaround),
    category: asString(item.category),
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

function parseEvidenceFreshness(snapshot: Record<string, unknown>, payload?: Record<string, unknown>): string | null {
  return (
    firstString(
      snapshot.probe_freshness,
      snapshot.freshness,
      snapshot.evidence_freshness,
      payload?.probe_freshness,
      payload?.freshness,
      payload?.evidence_freshness,
    )
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
  const failureSource = asItems(snapshot.active_failures).length > 0
    ? snapshot.active_failures
    : payload.failure_modes;
  const activeFailures = asItems(failureSource)
    .map((item) => parseFailureMode(item))
    .filter((item): item is ServiceFailureMode => item !== null);
  const alternatives = asItems(snapshot.alternatives ?? payload.alternatives)
    .map((item) => parseAlternative(item))
    .filter((item): item is ServiceAlternative => item !== null);

  const autonomyTier = firstString(payload.autonomy_tier)
    ?? (() => {
      const autonomyScore = firstNumber(payload.autonomy_score, snapshot.autonomy_score);
      if (autonomyScore === null) return null;
      if (autonomyScore >= 7.5) return "L4";
      if (autonomyScore >= 6.0) return "L3";
      if (autonomyScore >= 5.0) return "L2";
      return "L1";
    })();

  return {
    serviceSlug,
    aggregateRecommendationScore: firstNumber(payload.aggregate_recommendation_score, payload.an_score, payload.score),
    executionScore: asNumber(payload.execution_score),
    accessReadinessScore: firstNumber(payload.access_readiness_score, payload.access_score),
    confidence: asNumber(payload.confidence),
    tier: asString(payload.tier),
    tierLabel: asString(payload.tier_label),
    explanation: asString(payload.explanation),
    calculatedAt: asString(payload.calculated_at),
    evidenceFreshness: parseEvidenceFreshness(snapshot, payload),
    activeFailures,
    alternatives,
    p1Score: firstNumber(payload.p1_score, payload.payment_autonomy),
    g1Score: firstNumber(payload.g1_score, payload.governance_readiness),
    w1Score: firstNumber(payload.w1_score, payload.web_accessibility),
    p1Rationale: firstString(payload.p1_rationale, isRecord(payload.autonomy) ? payload.autonomy.p1_rationale : null),
    g1Rationale: firstString(payload.g1_rationale, isRecord(payload.autonomy) ? payload.autonomy.g1_rationale : null),
    w1Rationale: firstString(payload.w1_rationale, isRecord(payload.autonomy) ? payload.autonomy.w1_rationale : null),
    autonomyTier,
    baseUrl: asString(payload.base_url),
    docsUrl: asString(payload.docs_url),
    openapiUrl: asString(payload.openapi_url),
    mcpServerUrl: asString(payload.mcp_server_url),
    evidenceTier: (asString(payload.evidence_tier) as EvidenceTier) ?? "assessed",
    evidenceTierLabel: asString(payload.evidence_tier_label) ?? "Assessed",
    evidenceCount: asNumber(payload.evidence_count) ?? 0,
    lastEvaluated: firstString(payload.last_evaluated, payload.calculated_at),
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
  const readiness = isRecord(data.readiness) ? data.readiness : {};
  const launchGates = isRecord(data.launch_gates) ? data.launch_gates : {};
  const executions = isRecord(data.executions) ? data.executions : {};
  const disputeClicks = isRecord(clicks.dispute_clicks) ? clicks.dispute_clicks : {};
  const servicePageCtaSplit = isRecord(clicks.service_page_cta_split) ? clicks.service_page_cta_split : {};
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

  const parseSplitRow = (row: unknown) => {
    if (!isRecord(row)) {
      return { clicks: 0, share: null };
    }

    return {
      clicks: asNumber(row.clicks) ?? 0,
      share: asNumber(row.share),
    };
  };

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
  const readinessSignals = asItems(readiness.signals).map((row) => ({
    key: asString(row.key) ?? "unknown",
    label: asString(row.label) ?? "Unknown signal",
    value: asNumber(row.value),
    target: asNumber(row.target),
    met: typeof row.met === "boolean" ? row.met : null,
    detail: asString(row.detail) ?? "",
  }));

  const parseGate = (row: unknown) => {
    if (!isRecord(row)) {
      return null;
    }

    const status = asString(row.status);
    if (
      status !== "ready"
      && status !== "not_ready"
      && status !== "blocked"
      && status !== "manual_review"
    ) {
      return null;
    }

    return {
      key: asString(row.key) ?? "unknown",
      label: asString(row.label) ?? "Unknown gate",
      status,
      headline: asString(row.headline) ?? "",
      summary: asString(row.summary) ?? "",
      nextAction: asString(row.next_action) ?? "",
      shouldNotify: Boolean(row.should_notify),
      audience: asString(row.audience) ?? "operators",
      signals: asItems(row.signals).map((signal) => ({
        key: asString(signal.key) ?? "unknown",
        label: asString(signal.label) ?? "Unknown signal",
        value: asNumber(signal.value),
        target: asNumber(signal.target),
        met: typeof signal.met === "boolean" ? signal.met : null,
        detail: asString(signal.detail) ?? "",
      })),
    };
  };

  const parseNotification = (row: unknown) => {
    if (!isRecord(row)) {
      return null;
    }

    const level = asString(row.level);
    if (level !== "action" && level !== "warning" && level !== "info") {
      return null;
    }

    return {
      key: asString(row.key) ?? "unknown",
      level,
      audience: asString(row.audience) ?? "operators",
      headline: asString(row.headline) ?? "",
      message: asString(row.message) ?? "",
    };
  };

  const parsedSmallGroupGate = parseGate(launchGates.small_group);
  const parsedPublicLaunchGate = parseGate(launchGates.public_launch);
  const notifications = asItems(data.notifications)
    .map(parseNotification)
    .filter((row): row is NonNullable<ReturnType<typeof parseNotification>> => row !== null);

  const window = asString(data.window);
  const startAt = asString(data.start_at);
  const generatedAt = asString(data.generated_at);
  const readinessStatus = asString(readiness.status);
  const readinessHeadline = asString(readiness.headline);
  const readinessSummary = asString(readiness.summary);
  const readinessNextFocus = asString(readiness.next_focus);

  if (
    (window !== "24h" && window !== "7d" && window !== "launch")
    || !startAt
    || !generatedAt
    || (
      readinessStatus !== "insufficient_signal"
      && readinessStatus !== "onboarding_friction"
      && readinessStatus !== "repeat_usage_gap"
      && readinessStatus !== "managed_path_gap"
      && readinessStatus !== "small_group_candidate"
    )
    || !readinessHeadline
    || !readinessSummary
    || !readinessNextFocus
    || !parsedSmallGroupGate
    || !parsedPublicLaunchGate
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
      providerClickSurfaces: parseDashboardCounts(clicks.provider_click_surfaces),
      providerCtr,
      servicePageCtaSplit: {
        servicePageClicks: asNumber(servicePageCtaSplit.service_page_clicks) ?? 0,
        outsideServicePageClicks: asNumber(servicePageCtaSplit.outside_service_page_clicks) ?? 0,
        hero: parseSplitRow(servicePageCtaSplit.hero),
        sidebar: parseSplitRow(servicePageCtaSplit.sidebar),
        legacyServicePage: parseSplitRow(servicePageCtaSplit.legacy_service_page),
        other: parseSplitRow(servicePageCtaSplit.other),
      },
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
    readiness: {
      status: readinessStatus,
      headline: readinessHeadline,
      summary: readinessSummary,
      nextFocus: readinessNextFocus,
      signals: readinessSignals,
    },
    launchGates: {
      smallGroup: parsedSmallGroupGate,
      publicLaunch: parsedPublicLaunchGate,
    },
    notifications,
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

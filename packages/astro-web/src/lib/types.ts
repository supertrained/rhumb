export type Service = {
  slug: string;
  name: string;
  category: string;
  description?: string;
};

export type ANScore = {
  score: number;
  confidence: number;
  tier: "emerging" | "developing" | "ready" | "native";
  explanation: string;
};

export type EvidenceTier = "pending" | "assessed" | "tested" | "verified";

export type ReviewTrustSource =
  | "docs_derived"
  | "tester_generated"
  | "runtime_verified"
  | "unknown";

export type ServiceReview = {
  id: string;
  headline: string | null;
  summary: string | null;
  reviewerLabel: string | null;
  reviewedAt: string | null;
  confidence: number | null;
  evidenceCount: number;
  trustSource: ReviewTrustSource;
};

export type LeaderboardItem = {
  serviceSlug: string;
  name: string;
  aggregateRecommendationScore: number | null;
  executionScore: number | null;
  accessReadinessScore: number | null;
  freshness: string | null;
  calculatedAt: string | null;
  tier: string | null;
  confidence: number | null;
  p1Score: number | null;
  g1Score: number | null;
  w1Score: number | null;
  evidenceTier: EvidenceTier;
  evidenceCount: number;
};

export type LeaderboardViewModel = {
  category: string;
  items: LeaderboardItem[];
  error: string | null;
};

export type ServiceFailureMode = {
  id: string | null;
  summary: string;
  description?: string;
  severity?: string;
  frequency?: string;
  agentImpact?: string | null;
  workaround?: string | null;
  category?: string;
};

export type CategorySummary = {
  slug: string;
  serviceCount: number;
};

export type ServiceAlternative = {
  serviceSlug: string;
  score: number | null;
};

export type ServiceScoreViewModel = {
  serviceSlug: string;
  aggregateRecommendationScore: number | null;
  executionScore: number | null;
  accessReadinessScore: number | null;
  confidence: number | null;
  tier: string | null;
  tierLabel: string | null;
  explanation: string | null;
  calculatedAt: string | null;
  evidenceFreshness: string | null;
  activeFailures: ServiceFailureMode[];
  alternatives: ServiceAlternative[];
  p1Score: number | null;
  g1Score: number | null;
  w1Score: number | null;
  p1Rationale: string | null;
  g1Rationale: string | null;
  w1Rationale: string | null;
  autonomyTier: string | null;
  baseUrl: string | null;
  docsUrl: string | null;
  openapiUrl: string | null;
  mcpServerUrl: string | null;
  evidenceTier: EvidenceTier;
  evidenceTierLabel: string;
  evidenceCount: number;
  lastEvaluated: string | null;
};

export type LaunchDashboardCount = {
  key: string;
  count: number;
};

export type LaunchDashboardCtrRow = {
  service_slug: string;
  clicks: number;
  views: number;
  ctr: number | null;
};

export type LaunchDashboardExecutionTrendRow = {
  period: string;
  total: number;
  successful: number;
  failed: number;
  successRate: number | null;
};

export type LaunchDashboardViewModel = {
  window: "24h" | "7d" | "launch";
  startAt: string;
  generatedAt: string;
  coverage: {
    publicServiceCount: number;
  };
  queries: {
    total: number;
    machineTotal: number;
    bySource: LaunchDashboardCount[];
    topQueryTypes: LaunchDashboardCount[];
    topServices: LaunchDashboardCount[];
    topSearches: LaunchDashboardCount[];
    uniqueClients: number;
    repeatClients: number;
    repeatClientRate: number | null;
    latestActivityAt: string | null;
  };
  clicks: {
    total: number;
    providerClicks: number;
    topProviderDomains: LaunchDashboardCount[];
    topSourceSurfaces: LaunchDashboardCount[];
    providerCtr: LaunchDashboardCtrRow[];
    disputeClicks: {
      email: number;
      github: number;
      contact: number;
    };
    latestActivityAt: string | null;
  };
  funnel: {
    queries: number;
    serviceViews: number;
    providerClicks: number;
    executeAttempts: number;
    successfulExecutes: number;
  };
  executions: {
    total: number;
    successful: number;
    failed: number;
    successRate: number | null;
    topCapabilities: LaunchDashboardCount[];
    successTrend: LaunchDashboardExecutionTrendRow[];
    latestActivityAt: string | null;
  };
};

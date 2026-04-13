import type {
  CategorySummary,
  EvidenceTier,
  LaunchDashboardViewModel,
  LeaderboardViewModel,
  Service,
  ServiceScoreViewModel,
} from "./types";

// Supabase direct mode (production) vs Python API mode (local dev)
const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL;
const SUPABASE_ANON_KEY = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/v1";

const useSupabase = Boolean(SUPABASE_URL && SUPABASE_ANON_KEY);

// ---------- Supabase helpers ----------

async function supabaseFetch<T>(path: string): Promise<T | null> {
  try {
    const response = await fetch(`${SUPABASE_URL}/rest/v1/${path}`, {
      headers: {
        apikey: SUPABASE_ANON_KEY!,
        Authorization: `Bearer ${SUPABASE_ANON_KEY!}`,
      },
      cache: "no-store",
    });
    if (!response.ok) return null;
    return (await response.json()) as T;
  } catch {
    return null;
  }
}

type SupabaseService = {
  slug: string;
  name: string;
  category: string;
  description: string | null;
};

type SupabaseScore = {
  service_slug: string;
  aggregate_recommendation_score: number | null;
  execution_score: number | null;
  access_readiness_score: number | null;
  confidence: number | null;
  tier: string | null;
  tier_label: string | null;
  probe_metadata: Record<string, unknown> | null;
  calculated_at: string | null;
  payment_autonomy: number | null;
  governance_readiness: number | null;
  web_accessibility: number | null;
  payment_autonomy_rationale: string | null;
  governance_readiness_rationale: string | null;
  web_accessibility_rationale: string | null;
  autonomy_score: number | null;
};

type SupabaseServiceLinks = {
  base_url: string | null;
  docs_url: string | null;
  openapi_url: string | null;
  mcp_server_url: string | null;
};

// ---------- Evidence tier helpers ----------

const EVIDENCE_TIER_LABELS: Record<EvidenceTier, string> = {
  pending: "Pending Evaluation",
  assessed: "Assessed",
  tested: "Tested",
  verified: "Verified",
};

function computeEvidenceTier(hasScore: boolean, runtimeEvidenceCount: number): EvidenceTier {
  if (!hasScore) return "pending";
  if (runtimeEvidenceCount >= 50) return "verified";
  if (runtimeEvidenceCount >= 1) return "tested";
  return "assessed";
}

type EvidenceStats = {
  count: number;
  latestAt: string | null;
};

async function getEvidenceStats(slug: string): Promise<EvidenceStats> {
  // Use Supabase HEAD request with Prefer: count=exact to get count + latest date
  // First get the count of runtime evidence records
  const records = await supabaseFetch<Array<{ created_at: string }>>(
    `evidence_records?service_slug=eq.${encodeURIComponent(slug)}&evidence_type=in.(runtime_verified,tester_generated)&select=created_at&order=created_at.desc`
  );
  if (!records || records.length === 0) {
    return { count: 0, latestAt: null };
  }
  return { count: records.length, latestAt: records[0].created_at };
}

async function getEvidenceCountsBatch(slugs: string[]): Promise<Record<string, number>> {
  if (slugs.length === 0) return {};
  const slugFilter = slugs.map((s) => `"${s}"`).join(",");
  const records = await supabaseFetch<Array<{ service_slug: string }>>(
    `evidence_records?service_slug=in.(${slugFilter})&evidence_type=in.(runtime_verified,tester_generated)&select=service_slug`
  );
  if (!records) return {};
  const counts: Record<string, number> = {};
  for (const r of records) {
    counts[r.service_slug] = (counts[r.service_slug] ?? 0) + 1;
  }
  return counts;
}

// ---------- Supabase implementations ----------

async function getServicesFromSupabase(): Promise<Service[]> {
  const data = await supabaseFetch<SupabaseService[]>(
    "services?select=slug,name,category,description&order=name.asc"
  );
  if (!data) return [];
  return data.map((s) => ({
    slug: s.slug,
    name: s.name,
    category: s.category,
    ...(s.description ? { description: s.description } : {}),
  }));
}

async function getLeaderboardFromSupabase(
  category: string,
  options?: { limit?: number }
): Promise<LeaderboardViewModel> {
  const limit = options?.limit ?? 50;

  // Get services in this category
  const services = await supabaseFetch<SupabaseService[]>(
    `services?category=eq.${encodeURIComponent(category)}&select=slug,name`
  );

  if (!services || services.length === 0) {
    // Try to get all categories to show helpful error
    const allServices = await supabaseFetch<{ category: string }[]>(
      "services?select=category"
    );
    const categories = [...new Set(allServices?.map((s) => s.category) ?? [])].sort();
    return {
      category,
      items: [],
      error: `Category not found. Available: ${categories.join(", ")}`,
    };
  }

  const slugs = services.map((s) => s.slug);
  const slugFilter = slugs.map((s) => `"${s}"`).join(",");
  const nameMap = Object.fromEntries(services.map((s) => [s.slug, s.name]));

  // Get scores ordered by recency so dedup keeps the LATEST score per service
  // (matches service page which uses calculated_at.desc)
  const scores = await supabaseFetch<SupabaseScore[]>(
    `scores?service_slug=in.(${slugFilter})&order=calculated_at.desc.nullslast&limit=${limit * 3}`
  );

  if (!scores) {
    return { category, items: [], error: "Unable to load scores." };
  }

  // Deduplicate: keep only the LATEST (most recent) entry per service_slug
  // Then sort by aggregate score descending for leaderboard ranking
  const seen = new Set<string>();
  const deduped = scores.filter((sc) => {
    if (seen.has(sc.service_slug)) return false;
    seen.add(sc.service_slug);
    return true;
  });
  deduped.sort((a, b) =>
    (b.aggregate_recommendation_score ?? 0) - (a.aggregate_recommendation_score ?? 0)
  );

  // Batch-fetch evidence counts for all services
  const evidenceCounts = await getEvidenceCountsBatch(deduped.map((sc) => sc.service_slug));

  const items = deduped.map((sc) => {
    const count = evidenceCounts[sc.service_slug] ?? 0;
    const tier = computeEvidenceTier(sc.aggregate_recommendation_score !== null, count);
    return {
      serviceSlug: sc.service_slug,
      name: nameMap[sc.service_slug] ?? sc.service_slug,
      aggregateRecommendationScore: sc.aggregate_recommendation_score,
      executionScore: sc.execution_score,
      accessReadinessScore: sc.access_readiness_score,
      freshness:
        (sc.probe_metadata as Record<string, string> | null)?.freshness ?? null,
      calculatedAt: sc.calculated_at,
      tier: sc.tier,
      confidence: sc.confidence,
      p1Score: sc.payment_autonomy ?? null,
      g1Score: sc.governance_readiness ?? null,
      w1Score: sc.web_accessibility ?? null,
      evidenceTier: tier,
      evidenceCount: count,
    };
  });

  return { category, items, error: null };
}

async function getServiceScoreFromSupabase(
  slug: string
): Promise<ServiceScoreViewModel | null> {
  // Get latest score for this service
  const scores = await supabaseFetch<SupabaseScore[]>(
    `scores?service_slug=eq.${encodeURIComponent(slug)}&order=calculated_at.desc&limit=1`
  );

  if (!scores || scores.length === 0) return null;
  const sc = scores[0];
  const serviceLinks = await supabaseFetch<SupabaseServiceLinks[]>(
    `services?slug=eq.${encodeURIComponent(slug)}&select=base_url,docs_url,openapi_url,mcp_server_url&limit=1`
  );
  const links = serviceLinks?.[0] ?? {
    base_url: null,
    docs_url: null,
    openapi_url: null,
    mcp_server_url: null,
  };

  // Fetch active failure modes from Supabase
  const failures = await supabaseFetch<Array<{
    id: string;
    title: string;
    description: string;
    severity: string;
    frequency: string;
    agent_impact: string | null;
    workaround: string | null;
    category: string;
  }>>(
    `failure_modes?service_slug=eq.${encodeURIComponent(slug)}&resolved_at=is.null&order=severity.asc`
  );

  const activeFailures = (failures ?? []).map(f => ({
    id: f.id,
    summary: f.title,
    description: f.description,
    severity: f.severity,
    frequency: f.frequency,
    agentImpact: f.agent_impact,
    workaround: f.workaround,
    category: f.category,
  }));

  // Fetch evidence stats for tier computation
  const evidence = await getEvidenceStats(slug);
  const evidenceTier = computeEvidenceTier(sc.aggregate_recommendation_score !== null, evidence.count);

  return {
    serviceSlug: sc.service_slug,
    aggregateRecommendationScore: sc.aggregate_recommendation_score,
    executionScore: sc.execution_score,
    accessReadinessScore: sc.access_readiness_score,
    confidence: sc.confidence,
    tier: sc.tier,
    tierLabel: sc.tier_label,
    explanation: null,
    calculatedAt: sc.calculated_at,
    evidenceFreshness:
      (sc.probe_metadata as Record<string, string> | null)?.freshness ?? null,
    activeFailures,
    alternatives: [],
    p1Score: sc.payment_autonomy ?? null,
    g1Score: sc.governance_readiness ?? null,
    w1Score: sc.web_accessibility ?? null,
    p1Rationale: sc.payment_autonomy_rationale ?? null,
    g1Rationale: sc.governance_readiness_rationale ?? null,
    w1Rationale: sc.web_accessibility_rationale ?? null,
    autonomyTier: sc.autonomy_score != null ? (sc.autonomy_score >= 7.5 ? 'L4' : sc.autonomy_score >= 6.0 ? 'L3' : sc.autonomy_score >= 5.0 ? 'L2' : 'L1') : null,
    baseUrl: links.base_url,
    docsUrl: links.docs_url,
    openapiUrl: links.openapi_url,
    mcpServerUrl: links.mcp_server_url,
    evidenceTier,
    evidenceTierLabel: EVIDENCE_TIER_LABELS[evidenceTier],
    evidenceCount: evidence.count,
    lastEvaluated: evidence.latestAt ?? sc.calculated_at,
  };
}

async function getCategoriesFromSupabase(): Promise<CategorySummary[]> {
  const data = await supabaseFetch<{ category: string }[]>("services?select=category");
  if (!data) return [];

  const counts: Record<string, number> = {};
  for (const row of data) {
    counts[row.category] = (counts[row.category] ?? 0) + 1;
  }
  return Object.entries(counts).map(([slug, serviceCount]) => ({ slug, serviceCount }));
}

// ---------- Python API implementations (original) ----------

import {
  parseLaunchDashboardResponse,
  parseLeaderboardResponse,
  parseServiceScoreResponse,
  parseServicesResponse,
} from "./adapters";

async function fetchPayload(path: string): Promise<unknown> {
  try {
    const response = await fetch(`${API_BASE}${path}`, {
      cache: "no-store",
      headers: {
        "X-Rhumb-Client": "web",
      },
    });
    if (!response.ok) return null;
    return (await response.json()) as unknown;
  } catch {
    return null;
  }
}

type LaunchDashboardAuthMode = "admin" | "dashboard";

async function fetchAdminPayload(path: string, adminKey: string): Promise<unknown> {
  try {
    const response = await fetch(`${API_BASE}${path}`, {
      cache: "no-store",
      headers: {
        "X-Rhumb-Admin-Key": adminKey,
        "X-Rhumb-Client": "web",
      },
    });
    if (!response.ok) return null;
    return (await response.json()) as unknown;
  } catch {
    return null;
  }
}

async function fetchLaunchDashboardPayload(
  path: string,
  accessKey: string,
  authMode: LaunchDashboardAuthMode,
): Promise<unknown> {
  try {
    const headerName = authMode === "dashboard"
      ? "X-Rhumb-Launch-Dashboard-Key"
      : "X-Rhumb-Admin-Key";
    const response = await fetch(`${API_BASE}${path}`, {
      cache: "no-store",
      headers: {
        [headerName]: accessKey,
        "X-Rhumb-Client": "web",
      },
    });
    if (!response.ok) return null;
    return (await response.json()) as unknown;
  } catch {
    return null;
  }
}

async function getServicesFromAPI(): Promise<Service[]> {
  const payload = await fetchPayload("/services?limit=500");
  return parseServicesResponse(payload);
}

async function getLeaderboardFromAPI(
  category: string,
  options?: { limit?: number }
): Promise<LeaderboardViewModel> {
  const params = new URLSearchParams();
  if (options?.limit !== undefined) {
    params.set("limit", String(options.limit));
  }
  const suffix = params.toString().length > 0 ? `?${params.toString()}` : "";
  const payload = await fetchPayload(
    `/leaderboard/${encodeURIComponent(category)}${suffix}`
  );
  if (payload === null) {
    return { category, items: [], error: "Unable to load leaderboard right now." };
  }
  const parsed = parseLeaderboardResponse(payload);
  return {
    ...parsed,
    category: parsed.category === "unknown" ? category : parsed.category,
  };
}

async function getServiceScoreFromAPI(
  slug: string
): Promise<ServiceScoreViewModel | null> {
  const payload = await fetchPayload(
    `/services/${encodeURIComponent(slug)}/score`
  );
  return parseServiceScoreResponse(payload);
}

// ---------- Exported functions (auto-select mode) ----------

/** Fetch all services. */
export async function getServices(): Promise<Service[]> {
  return useSupabase ? getServicesFromSupabase() : getServicesFromAPI();
}

/** Fetch category leaderboard. */
export async function getLeaderboard(
  category: string,
  options?: { limit?: number }
): Promise<LeaderboardViewModel> {
  return useSupabase
    ? getLeaderboardFromSupabase(category, options)
    : getLeaderboardFromAPI(category, options);
}

/** Fetch latest score details for one service. */
export async function getServiceScore(
  slug: string
): Promise<ServiceScoreViewModel | null> {
  return useSupabase
    ? getServiceScoreFromSupabase(slug)
    : getServiceScoreFromAPI(slug);
}

/** Fetch all categories with service counts. */
export async function getCategories(): Promise<CategorySummary[]> {
  if (useSupabase) return getCategoriesFromSupabase();
  // In API mode, derive from services list
  const services = await getServicesFromAPI();
  const counts: Record<string, number> = {};
  for (const s of services) {
    counts[s.category] = (counts[s.category] ?? 0) + 1;
  }
  return Object.entries(counts).map(([slug, serviceCount]) => ({ slug, serviceCount }));
}

/** Fetch total number of scored services (services with a score row). */
export async function getServiceCount(): Promise<number> {
  if (useSupabase) {
    // Count from services table (all indexed services), not scores table
    const data = await supabaseFetch<Array<{ slug: string }>>(
      "services?select=slug"
    );
    if (!data) return 0;
    return data.length;
  }
  const services = await getServicesFromAPI();
  return services.length;
}

/** Fetch total number of published capabilities. */
export async function getCapabilityCount(): Promise<number> {
  if (useSupabase) {
    const data = await supabaseFetch<Array<{ id: string }>>("capabilities?select=id");
    return data?.length ?? 0;
  }

  const payload = await fetchPayload("/capabilities?limit=1");
  if (!payload || typeof payload !== "object" || !("data" in payload)) {
    return 0;
  }

  const data = payload.data;
  if (!data || typeof data !== "object" || !("total" in data)) {
    return 0;
  }

  return typeof data.total === "number" ? data.total : 0;
}

/** Fetch launch dashboard data from the admin API. */
export async function getLaunchDashboard(
  window: "24h" | "7d" | "launch",
  accessKey: string,
  authMode: LaunchDashboardAuthMode = "dashboard",
): Promise<LaunchDashboardViewModel | null> {
  const payload = await fetchLaunchDashboardPayload(
    `/admin/launch/dashboard?window=${encodeURIComponent(window)}`,
    accessKey,
    authMode,
  );
  return parseLaunchDashboardResponse(payload);
}

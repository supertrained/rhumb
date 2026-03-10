import type { CategorySummary, LeaderboardViewModel, Service, ServiceScoreViewModel } from "./types";

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
  p1_score: number | null;
  g1_score: number | null;
  w1_score: number | null;
  p1_rationale: string | null;
  g1_rationale: string | null;
  w1_rationale: string | null;
  autonomy_tier: string | null;
};

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

  // Get latest score for each service (use order + distinct on via limit)
  const scores = await supabaseFetch<SupabaseScore[]>(
    `scores?service_slug=in.(${slugFilter})&order=aggregate_recommendation_score.desc.nullslast&limit=${limit}`
  );

  if (!scores) {
    return { category, items: [], error: "Unable to load scores." };
  }

  // Deduplicate: keep only the highest-scored entry per service_slug
  const seen = new Set<string>();
  const items = scores
    .filter((sc) => {
      if (seen.has(sc.service_slug)) return false;
      seen.add(sc.service_slug);
      return true;
    })
    .map((sc) => ({
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
      p1Score: sc.p1_score ?? null,
      g1Score: sc.g1_score ?? null,
      w1Score: sc.w1_score ?? null,
    }));

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
    activeFailures: [],
    alternatives: [],
    p1Score: sc.p1_score ?? null,
    g1Score: sc.g1_score ?? null,
    w1Score: sc.w1_score ?? null,
    p1Rationale: sc.p1_rationale ?? null,
    g1Rationale: sc.g1_rationale ?? null,
    w1Rationale: sc.w1_rationale ?? null,
    autonomyTier: sc.autonomy_tier ?? null,
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

import { parseLeaderboardResponse, parseServiceScoreResponse, parseServicesResponse } from "./adapters";

async function fetchPayload(path: string): Promise<unknown> {
  try {
    const response = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
    if (!response.ok) return null;
    return (await response.json()) as unknown;
  } catch {
    return null;
  }
}

async function getServicesFromAPI(): Promise<Service[]> {
  const payload = await fetchPayload("/services");
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

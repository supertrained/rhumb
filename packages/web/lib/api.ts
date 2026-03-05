import { parseLeaderboardResponse, parseServiceScoreResponse, parseServicesResponse } from "./adapters";
import type { LeaderboardViewModel, Service, ServiceScoreViewModel } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/v1";

async function fetchPayload(path: string): Promise<unknown> {
  try {
    const response = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
    if (!response.ok) {
      return null;
    }

    return (await response.json()) as unknown;
  } catch {
    return null;
  }
}

/** Fetch all services. */
export async function getServices(): Promise<Service[]> {
  const payload = await fetchPayload("/services");
  return parseServicesResponse(payload);
}

/** Fetch category leaderboard. */
export async function getLeaderboard(
  category: string,
  options?: { limit?: number }
): Promise<LeaderboardViewModel> {
  const params = new URLSearchParams();
  if (options?.limit !== undefined) {
    params.set("limit", String(options.limit));
  }

  const suffix = params.toString().length > 0 ? `?${params.toString()}` : "";
  const payload = await fetchPayload(`/leaderboard/${encodeURIComponent(category)}${suffix}`);
  if (payload === null) {
    return {
      category,
      items: [],
      error: "Unable to load leaderboard right now."
    };
  }

  const parsed = parseLeaderboardResponse(payload);
  return {
    ...parsed,
    category: parsed.category === "unknown" ? category : parsed.category
  };
}

/** Fetch latest score details for one service. */
export async function getServiceScore(slug: string): Promise<ServiceScoreViewModel | null> {
  const payload = await fetchPayload(`/services/${encodeURIComponent(slug)}/score`);
  return parseServiceScoreResponse(payload);
}

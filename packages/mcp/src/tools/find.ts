/**
 * find_services — Semantic search for indexed Services, ranked by AN Score
 *
 * Calls the Rhumb API to search Services and returns results
 * sorted by aggregateScore descending.
 */

import type { FindServiceInput, FindServiceOutput } from "../types.js";
import type { RhumbApiClient } from "../api-client.js";

const DEFAULT_LIMIT = 10;
const MAX_LIMIT = 50;

/**
 * Handle a find_services request.
 *
 * @param input  Validated tool input (query + optional limit)
 * @param client API client for fetching Services
 * @returns      Ranked Service results; empty array on any error (resilient)
 */
export async function handleFindServices(
  input: FindServiceInput,
  client: RhumbApiClient
): Promise<FindServiceOutput> {
  const limit = Math.min(Math.max(input.limit ?? DEFAULT_LIMIT, 1), MAX_LIMIT);

  try {
    const services = await client.searchServices(input.query);

    // Sort by aggregateScore descending — nulls sink to bottom
    const sorted = [...services].sort((a, b) => {
      if (a.aggregateScore === null && b.aggregateScore === null) return 0;
      if (a.aggregateScore === null) return 1;
      if (b.aggregateScore === null) return -1;
      return b.aggregateScore - a.aggregateScore;
    });

    return {
      services: sorted.slice(0, limit).map((s) => ({
        name: s.name,
        slug: s.slug,
        aggregateScore: s.aggregateScore,
        executionScore: s.executionScore,
        accessScore: s.accessScore,
        explanation: s.explanation
      }))
    };
  } catch {
    // Resilient fallback: return empty array on any error
    return { services: [] };
  }
}

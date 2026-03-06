/**
 * find_tools — Semantic search for agent tools, ranked by AN Score
 *
 * Calls the Rhumb API to search services and returns results
 * sorted by aggregateScore descending.
 */

import type { FindToolInput, FindToolOutput } from "../types.js";
import type { RhumbApiClient } from "../api-client.js";

const DEFAULT_LIMIT = 10;
const MAX_LIMIT = 50;

/**
 * Handle a find_tools request.
 *
 * @param input  Validated tool input (query + optional limit)
 * @param client API client for fetching services
 * @returns      Ranked tool results; empty array on any error (resilient)
 */
export async function handleFindTools(
  input: FindToolInput,
  client: RhumbApiClient
): Promise<FindToolOutput> {
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
      tools: sorted.slice(0, limit).map((s) => ({
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
    return { tools: [] };
  }
}

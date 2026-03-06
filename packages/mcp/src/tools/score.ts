/**
 * get_score — Detailed AN Score breakdown for a single service
 *
 * Calls the Rhumb API to fetch the full score breakdown
 * for the specified service slug.
 */

import type { GetScoreInput, GetScoreOutput } from "../types.js";
import type { RhumbApiClient } from "../api-client.js";

/**
 * Handle a get_score request.
 *
 * @param input  Validated tool input (slug)
 * @param client API client for fetching the score
 * @returns      Full score breakdown; error response with message on failure
 */
export async function handleGetScore(
  input: GetScoreInput,
  client: RhumbApiClient
): Promise<GetScoreOutput> {
  try {
    const score = await client.getServiceScore(input.slug);

    if (!score) {
      return {
        slug: input.slug,
        aggregateScore: null,
        executionScore: null,
        accessScore: null,
        confidence: 0,
        tier: "unknown",
        explanation: `Service '${input.slug}' not found`,
        freshness: "unknown"
      };
    }

    return score;
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    return {
      slug: input.slug,
      aggregateScore: null,
      executionScore: null,
      accessScore: null,
      confidence: 0,
      tier: "unknown",
      explanation: `Failed to fetch score: ${message}`,
      freshness: "unknown"
    };
  }
}

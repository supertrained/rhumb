/**
 * get_alternatives — Find alternative services ranked by AN Score
 *
 * Extracts failure-mode tags from the current service's score response,
 * searches for peer services sharing those tags, and returns peers
 * with higher aggregateScore ranked descending.
 */

import type { GetAlternativesInput, GetAlternativesOutput } from "../types.js";
import type { RhumbApiClient } from "../api-client.js";

/**
 * Handle a get_alternatives request.
 *
 * @param input  Validated tool input (slug)
 * @param client API client for fetching services
 * @returns      Ranked alternative services; empty array on any error (resilient)
 */
export async function handleGetAlternatives(
  input: GetAlternativesInput,
  client: RhumbApiClient
): Promise<GetAlternativesOutput> {
  try {
    const indexedAlternatives = await client.getServiceAlternatives?.(input.slug);
    if (indexedAlternatives && indexedAlternatives.length > 0) {
      return { alternatives: indexedAlternatives };
    }

    const score = await client.getServiceScore(input.slug);
    if (!score) return { alternatives: [] };

    const tags = score.tags;
    if (tags.length === 0) return { alternatives: [] };

    // Search for peer services using each failure tag
    const searchPromises = tags.map((tag) => client.searchServices(tag));
    const results = await Promise.all(searchPromises);
    const allPeers = results.flat();

    // Deduplicate, exclude current service, filter to higher scores
    const currentScore = score.aggregateScore ?? 0;
    const seen = new Set<string>();
    const sharedTags = tags.join(", ");

    const alternatives = allPeers
      .filter((peer) => {
        if (peer.slug === input.slug) return false;
        if (seen.has(peer.slug)) return false;
        seen.add(peer.slug);
        return (peer.aggregateScore ?? 0) > currentScore;
      })
      .sort((a, b) => (b.aggregateScore ?? 0) - (a.aggregateScore ?? 0))
      .map((peer) => ({
        name: peer.name,
        slug: peer.slug,
        aggregateScore: peer.aggregateScore,
        reason: `Higher AN Score alternative (shared failure patterns: ${sharedTags})`
      }));

    return { alternatives };
  } catch {
    // Resilient fallback: return empty array on any error
    return { alternatives: [] };
  }
}

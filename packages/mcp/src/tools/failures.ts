/**
 * get_failure_modes — Known failure patterns for a service
 *
 * Calls the Rhumb API to fetch the service score and extracts
 * the failure_modes array, mapping each to the output contract.
 */

import type { GetFailureModesInput, GetFailureModesOutput } from "../types.js";
import type { RhumbApiClient } from "../api-client.js";

/**
 * Handle a get_failure_modes request.
 *
 * @param input  Validated tool input (slug)
 * @param client API client for fetching the service score
 * @returns      Failure modes array; empty array on any error (resilient)
 */
export async function handleGetFailureModes(
  input: GetFailureModesInput,
  client: RhumbApiClient
): Promise<GetFailureModesOutput> {
  try {
    const score = await client.getServiceScore(input.slug);
    if (!score) return { failures: [] };

    return {
      failures: score.failureModes.map((fm) => ({
        pattern: fm.pattern,
        impact: fm.impact,
        frequency: fm.frequency,
        workaround: fm.workaround
      }))
    };
  } catch {
    // Resilient fallback: return empty array on any error
    return { failures: [] };
  }
}

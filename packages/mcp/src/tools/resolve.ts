/**
 * resolve_capability tool handler
 *
 * Resolves a capability to ranked providers with health-aware recommendations.
 * The core agent decision: "I need email.send — what should I use?"
 */

import type { RhumbApiClient } from "../api-client.js";
import type { ResolveCapabilityInput, ResolveCapabilityOutput } from "../types.js";

export async function handleResolveCapability(
  input: ResolveCapabilityInput,
  client: RhumbApiClient
): Promise<ResolveCapabilityOutput> {
  try {
    const result = await client.resolveCapability(input.capability);

    if (!result) {
      return {
        capability: input.capability,
        providers: [],
        fallbackChain: [],
        relatedBundles: [],
        executeHint: null,
        recoveryHint: null
      };
    }

    return result;
  } catch {
    return {
      capability: input.capability,
      providers: [],
      fallbackChain: [],
      relatedBundles: [],
      executeHint: null,
      recoveryHint: null
    };
  }
}

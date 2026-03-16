/**
 * discover_capabilities tool handler
 *
 * Searches for agent capabilities across domains.
 * Agents ask "what can I do?" — this returns the answer.
 */

import type { RhumbApiClient } from "../api-client.js";
import type { DiscoverCapabilitiesInput, DiscoverCapabilitiesOutput } from "../types.js";

export async function handleDiscoverCapabilities(
  input: DiscoverCapabilitiesInput,
  client: RhumbApiClient
): Promise<DiscoverCapabilitiesOutput> {
  try {
    const result = await client.discoverCapabilities({
      domain: input.domain,
      search: input.search,
      limit: input.limit ?? 20
    });

    return {
      capabilities: result.items,
      total: result.total
    };
  } catch {
    return { capabilities: [], total: 0 };
  }
}

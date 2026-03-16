/**
 * routing tool handler
 *
 * Get or set agent routing strategy:
 * - action="get" (default): see current strategy
 * - action="set": update to cheapest/fastest/highest_quality/balanced
 */

import type { RhumbApiClient } from "../api-client.js";
import type { RoutingInput, RoutingOutput } from "../types.js";

export async function handleRouting(
  input: RoutingInput,
  client: RhumbApiClient
): Promise<RoutingOutput> {
  const action = input.action || "get";

  if (action === "set" && input.strategy) {
    const result = await client.setRoutingStrategy(
      input.strategy,
      input.quality_floor,
      input.max_cost_per_call_usd
    );
    return result as unknown as RoutingOutput;
  }

  const result = await client.getRoutingStrategy();
  return result as unknown as RoutingOutput;
}

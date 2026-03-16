/**
 * estimate_capability tool handler
 *
 * Get cost estimate for executing a capability without actually
 * executing it. Use before expensive operations or when building
 * cost-aware workflows.
 */

import type { RhumbApiClient } from "../api-client.js";
import type { EstimateCapabilityInput, EstimateCapabilityOutput } from "../types.js";

export async function handleEstimateCapability(
  input: EstimateCapabilityInput,
  client: RhumbApiClient
): Promise<EstimateCapabilityOutput> {
  const result = await client.estimateCapability(input.capability_id, {
    provider: input.provider,
    credentialMode: input.credential_mode
  });

  return result;
}

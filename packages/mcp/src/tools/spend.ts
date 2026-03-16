/**
 * spend tool handler
 *
 * Returns spend breakdown by capability and provider for a given period.
 */

import type { RhumbApiClient } from "../api-client.js";
import type { SpendInput, SpendOutput } from "../types.js";

export async function handleSpend(
  input: SpendInput,
  client: RhumbApiClient
): Promise<SpendOutput> {
  const result = await client.getSpend(input.period);
  return result as unknown as SpendOutput;
}

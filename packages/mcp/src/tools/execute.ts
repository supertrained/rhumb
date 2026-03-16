/**
 * execute_capability tool handler
 *
 * Execute a capability through Rhumb. Resolves the best provider
 * automatically if none specified. Returns upstream response with
 * provider used and cost.
 */

import type { RhumbApiClient } from "../api-client.js";
import type { ExecuteCapabilityInput, ExecuteCapabilityOutput } from "../types.js";

export async function handleExecuteCapability(
  input: ExecuteCapabilityInput,
  client: RhumbApiClient
): Promise<ExecuteCapabilityOutput> {
  const result = await client.executeCapability(input.capability_id, {
    provider: input.provider,
    method: input.method,
    path: input.path,
    body: input.body,
    params: input.params,
    credentialMode: input.credential_mode,
    idempotencyKey: input.idempotency_key,
    agentToken: input.agent_token
  });

  return result;
}

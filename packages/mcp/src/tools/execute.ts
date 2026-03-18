/**
 * execute_capability tool handler
 *
 * Execute a capability through Rhumb. Resolves the best provider
 * automatically if none specified. Returns upstream response with
 * provider used and cost.
 *
 * Supports x402 zero-signup payment flow:
 *   1. Call without API key or payment → get paymentRequired with instructions
 *   2. Submit on-chain USDC payment
 *   3. Call again with x_payment containing tx proof → execution proceeds
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
    agentToken: input.agent_token,
    xPayment: input.x_payment
  });

  return result;
}

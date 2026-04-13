/**
 * check_credentials tool handler
 *
 * Returns the agent's credential status across all three modes:
 * - Mode 1 (BYOK): which Services have agent-provided credentials
 * - Mode 2 (Rhumb Resolve): which Capabilities are zero-config
 * - Mode 3 (Agent Vault): which Services have ceremony skills available
 *
 * This is the starting point for an agent to understand what it can
 * execute and what credentials it still needs.
 */

import type { RhumbApiClient } from "../api-client.js";
import type { CheckCredentialsInput, CheckCredentialsOutput } from "../types.js";

export async function handleCheckCredentials(
  input: CheckCredentialsInput,
  client: RhumbApiClient
): Promise<CheckCredentialsOutput> {
  // Fetch managed capabilities and ceremonies in parallel
  const [managed, ceremonies] = await Promise.all([
    client.listManagedCapabilities(),
    client.listCeremonies(),
  ]);

  const modes = [
    {
      mode: "byok",
      available: true,
      detail: "BYOK. Set RHUMB_API_KEY env var and pass credentials via the call.",
    },
    {
      mode: "rhumb_managed",
      available: managed.length > 0,
      detail: managed.length > 0
        ? `${managed.length} zero-config Capability(ies) available through Rhumb Resolve. No credentials needed — omit credential_mode or use credential_mode=auto to prefer Rhumb Resolve when available.`
        : "No managed capabilities currently available.",
    },
    {
      mode: "agent_vault",
      available: ceremonies.length > 0,
      detail: ceremonies.length > 0
        ? `${ceremonies.length} ceremony guide(s) available. Get your own API key following the guide, then pass it per call via the agent_token parameter.`
        : "No ceremony guides available yet.",
    },
  ];

  return {
    modes,
    managedCapabilities: managed.map((m) => ({
      capabilityId: m.capability_id,
      service: m.service_slug,
      description: m.description,
    })),
    availableCeremonies: ceremonies.length,
  };
}

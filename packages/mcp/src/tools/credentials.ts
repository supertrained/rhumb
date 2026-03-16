/**
 * check_credentials tool handler
 *
 * Returns the agent's credential status across all three modes:
 * - Mode 1 (BYO): which services have agent-provided credentials
 * - Mode 2 (Rhumb Managed): which capabilities are zero-config
 * - Mode 3 (Agent Vault): which services have ceremony skills available
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
      mode: "byo",
      available: true,
      detail: "Bring your own token. Set RHUMB_API_KEY env var and pass credentials via the execute call.",
    },
    {
      mode: "rhumb_managed",
      available: managed.length > 0,
      detail: managed.length > 0
        ? `${managed.length} zero-config capability(ies) available. No credentials needed — just call execute with credential_mode=rhumb_managed.`
        : "No managed capabilities currently available.",
    },
    {
      mode: "agent_vault",
      available: ceremonies.length > 0,
      detail: ceremonies.length > 0
        ? `${ceremonies.length} ceremony guide(s) available. Get your own API key following the guide, then pass it per-request via agent_token parameter.`
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

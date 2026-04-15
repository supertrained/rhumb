/**
 * check_credentials tool handler
 *
 * Returns live credential-mode readiness to the agent across the available credential paths,
 * now anchored to the same readiness surfaces the product exposes:
 * - /v1/agent/credentials for account-specific configured bridges and direct bundles
 * - /v1/capabilities/{id}/credential-modes for capability-specific provider readiness
 * - ceremony + managed-capability listings for self-serve and zero-config guidance
 *
 * This is the starting point for an agent to understand what it can
 * execute and what credentials it still needs.
 */

import type { RhumbApiClient } from "../api-client.js";
import type { CheckCredentialsInput, CheckCredentialsOutput } from "../types.js";

function summarizeList(items: string[], limit = 3): string {
  const unique = [...new Set(items.filter((item) => item.length > 0))];
  if (unique.length === 0) return "none";
  const shown = unique.slice(0, limit);
  const remainder = unique.length - shown.length;
  return remainder > 0 ? `${shown.join(", ")}, +${remainder} more` : shown.join(", ");
}

export async function handleCheckCredentials(
  input: CheckCredentialsInput,
  client: RhumbApiClient
): Promise<CheckCredentialsOutput> {
  const [managed, ceremonies, agentReadiness, capabilityReadiness] = await Promise.all([
    client.listManagedCapabilities(),
    client.listCeremonies(),
    input.capability
      ? Promise.resolve(null)
      : client.getAgentCredentialReadiness
        ? client.getAgentCredentialReadiness()
        : Promise.resolve(null),
    input.capability
      ? client.getCapabilityCredentialModes
        ? client.getCapabilityCredentialModes(input.capability)
        : Promise.resolve(null)
      : Promise.resolve(null),
  ]);

  const ceremonyServices = new Set(ceremonies.map((ceremony) => ceremony.service_slug));

  if (input.capability) {
    if (!capabilityReadiness) {
      return {
        modes: [
          {
            mode: "byok",
            available: true,
            detail: `Credential readiness did not load for ${input.capability}. BYOK and Agent Vault are provider-controlled paths and may or may not be available for this capability. Retry this check, or call resolve to see live providers and setup hints.`,
          },
          {
            mode: "rhumb_managed",
            available: managed.length > 0,
            detail: managed.length > 0
              ? `${managed.length} zero-config Capability(ies) are live through Rhumb Resolve, but this capability-specific readiness check did not load.`
              : "No zero-config managed capabilities are currently listed.",
          },
          {
            mode: "agent_vault",
            available: ceremonies.length > 0,
            detail: ceremonies.length > 0
              ? `${ceremonies.length} ceremony guide(s) are available, but this capability-specific readiness check did not load.`
              : "No ceremony guides are currently listed.",
          },
        ],
        managedCapabilities: managed.map((m) => ({
          capabilityId: m.capability_id,
          service: m.service_slug,
          description: m.description,
        })),
        availableCeremonies: ceremonies.length,
        capability: input.capability,
        providers: [],
        error: `Couldn't load credential-mode readiness for ${input.capability}.`,
      };
    }

    const providers = capabilityReadiness.providers.map((provider) => ({
      service: provider.serviceSlug,
      authMethod: provider.authMethod,
      anyConfigured: provider.anyConfigured,
      modes: provider.modes.map((mode) => ({
        mode: mode.mode,
        available: mode.available,
        configured: mode.configured,
        setupHint: mode.setupHint,
        ceremonyAvailable: ceremonyServices.has(provider.serviceSlug),
      })),
    }));

    const providersForMode = (modeName: string) => providers.filter((provider) => provider.modes.some((mode) => mode.mode === modeName));
    const configuredProvidersForMode = (modeName: string) => providers.filter((provider) => provider.modes.some((mode) => mode.mode === modeName && mode.configured));

    const byokProviders = providersForMode("byok");
    const byokConfigured = configuredProvidersForMode("byok");
    const managedProviders = providersForMode("rhumb_managed");
    const vaultProviders = providersForMode("agent_vault");
    const ceremonyProviders = vaultProviders.filter((provider) => ceremonyServices.has(provider.service));

    return {
      modes: [
        {
          mode: "byok",
          available: byokProviders.length > 0,
          detail: byokProviders.length === 0
            ? `No BYOK path is exposed for ${capabilityReadiness.capabilityId}.`
            : byokConfigured.length > 0
              ? `BYOK is already configured for ${summarizeList(byokConfigured.map((provider) => provider.service))}.`
              : `BYOK is supported by ${summarizeList(byokProviders.map((provider) => provider.service))}; follow the provider setup hint to unlock it.`,
        },
        {
          mode: "rhumb_managed",
          available: managedProviders.length > 0,
          detail: managedProviders.length > 0
            ? `Governed execution (X-Rhumb-Key) is available through ${summarizeList(managedProviders.map((provider) => provider.service))}. No provider API key required for those providers.`
            : `No governed execution (X-Rhumb-Key) path is exposed for ${capabilityReadiness.capabilityId}.`,
        },
        {
          mode: "agent_vault",
          available: vaultProviders.length > 0,
          detail: vaultProviders.length === 0
            ? `No ceremony-guided setup path is exposed for ${capabilityReadiness.capabilityId}.`
            : ceremonyProviders.length > 0
              ? `Ceremony-guided setup is available for ${summarizeList(ceremonyProviders.map((provider) => provider.service))}.`
              : `Agent Vault mode is exposed for ${summarizeList(vaultProviders.map((provider) => provider.service))}, but no public ceremony guide is currently listed for those providers.`,
        },
      ],
      managedCapabilities: managed.map((m) => ({
        capabilityId: m.capability_id,
        service: m.service_slug,
        description: m.description,
      })),
      availableCeremonies: ceremonies.length,
      capability: capabilityReadiness.capabilityId,
      providers,
    };
  }

  const byokDetail = agentReadiness
    ? agentReadiness.configuredCount > 0
      ? `${agentReadiness.configuredCount} BYOK bridge(s) or direct bundle(s) are already configured: ${summarizeList(agentReadiness.configuredServices)}. ${agentReadiness.unlockedCount} capability(ies) are ready now, ${agentReadiness.lockedCount} still need setup.`
      : `${agentReadiness.unlockedCount} capability(ies) are ready now through governed rails (X-Rhumb-Key), but no BYOK bridges or direct bundles are configured on this agent yet.`
    : "Set RHUMB_API_KEY to see your configured BYOK bridges and direct bundles.";

  const modes = [
    {
      mode: "byok",
      available: true,
      detail: byokDetail,
    },
    {
      mode: "rhumb_managed",
      available: managed.length > 0,
      detail: managed.length > 0
        ? `${managed.length} governed Capability(ies) available through Rhumb Resolve. Execution uses X-Rhumb-Key (governed API key or wallet-prefund). No provider API keys needed. Omit credential_mode or use credential_mode=auto to prefer governed execution when available.`
        : "No managed capabilities currently available.",
    },
    {
      mode: "agent_vault",
      available: ceremonies.length > 0,
      detail: ceremonies.length > 0
        ? `${ceremonies.length} ceremony guide(s) available. Get your own provider API key following the guide, then pass it per call via the agent_token parameter.`
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
    agentReadiness: agentReadiness
      ? {
          configuredServices: agentReadiness.configuredServices,
          configuredCount: agentReadiness.configuredCount,
          unlockedCapabilities: agentReadiness.unlockedCapabilities,
          unlockedCount: agentReadiness.unlockedCount,
          lockedCapabilities: agentReadiness.lockedCapabilities,
          lockedCount: agentReadiness.lockedCount,
          totalCapabilities: agentReadiness.totalCapabilities,
        }
      : undefined,
  };
}

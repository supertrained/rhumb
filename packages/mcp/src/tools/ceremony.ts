/**
 * credential_ceremony tool handler
 *
 * Returns structured auth guides (ceremony skills) that teach agents
 * how to obtain their own API credentials for a service.
 *
 * Without a service param → lists all available ceremonies.
 * With a service param → returns detailed steps for that service.
 */

import type { RhumbApiClient } from "../api-client.js";
import type { CredentialCeremonyInput, CredentialCeremonyOutput } from "../types.js";

export async function handleCredentialCeremony(
  input: CredentialCeremonyInput,
  client: RhumbApiClient
): Promise<CredentialCeremonyOutput> {
  // If a specific service is requested, return detailed ceremony
  if (input.service) {
    const ceremony = await client.getCeremony(input.service);
    if (!ceremony) {
      return { count: 0 };
    }

    return {
      ceremony: {
        service: ceremony.service_slug,
        displayName: ceremony.display_name,
        description: ceremony.description,
        authType: ceremony.auth_type,
        difficulty: ceremony.difficulty,
        estimatedMinutes: ceremony.estimated_minutes,
        requiresHuman: ceremony.requires_human,
        documentationUrl: ceremony.documentation_url,
        steps: ceremony.steps,
        tokenPrefix: ceremony.token_prefix,
        tokenPattern: ceremony.token_pattern,
        verifyEndpoint: ceremony.verify_endpoint,
      },
      count: 1,
    };
  }

  // List all ceremonies
  const ceremonies = await client.listCeremonies();
  return {
    ceremonies: ceremonies.map((c) => ({
      service: c.service_slug,
      displayName: c.display_name,
      description: c.description,
      authType: c.auth_type,
      difficulty: c.difficulty,
      estimatedMinutes: c.estimated_minutes,
      requiresHuman: c.requires_human,
      documentationUrl: c.documentation_url,
    })),
    count: ceremonies.length,
  };
}

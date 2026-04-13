import { afterEach, describe, expect, it, vi } from "vitest";

import { createApiClient } from "../src/api-client.js";

describe("Rhumb MCP API client resolveCapability", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("parses execute and recovery hints from /resolve", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        data: {
          capability: "email.send",
          providers: [
            {
              service_slug: "resend",
              service_name: "Resend",
              an_score: 7.9,
              cost_per_call: null,
              free_tier_calls: 100,
              auth_method: "api_key",
              endpoint_pattern: "/emails",
              recommendation: "preferred",
              recommendation_reason: "Top ranked",
              credential_modes: ["byok"],
              configured: false,
              available_for_execute: false,
              circuit_state: "open"
            },
            {
              service_slug: "sendgrid",
              service_name: "SendGrid",
              an_score: 6.4,
              cost_per_call: 0.001,
              free_tier_calls: 100,
              auth_method: "api_key",
              endpoint_pattern: "/v3/mail/send",
              recommendation: "available",
              recommendation_reason: "Healthy fallback",
              credential_modes: ["byok"],
              configured: true,
              available_for_execute: true,
              circuit_state: "closed"
            }
          ],
          fallback_chain: ["sendgrid"],
          related_bundles: ["email.compose_and_deliver"],
          execute_hint: {
            preferred_provider: "sendgrid",
            selection_reason: "higher_ranked_provider_unavailable",
            skipped_provider_slugs: ["resend"],
            unavailable_provider_slugs: ["resend"],
            not_execute_ready_provider_slugs: [],
            endpoint_pattern: "/v3/mail/send",
            estimated_cost_usd: 0.001,
            auth_method: "api_key",
            credential_modes: ["byok"],
            configured: true,
            credential_modes_url: "/v1/capabilities/email.send/credential-modes",
            preferred_credential_mode: "byok",
            fallback_providers: ["amazon-ses"],
            setup_hint: null,
            setup_url: null
          },
          recovery_hint: {
            reason: "no_execute_ready_providers",
            requested_credential_mode: "byok",
            credential_modes_url: "/v1/capabilities/email.send/credential-modes",
            supported_provider_slugs: ["resend", "sendgrid"],
            supported_credential_modes: ["agent_vault", "byok"],
            unavailable_provider_slugs: ["resend"],
            not_execute_ready_provider_slugs: ["postmark"]
          }
        }
      })
    });
    vi.stubGlobal("fetch", fetchMock);

    const client = createApiClient("https://api.example.com/v1");
    const result = await client.resolveCapability("email.send");

    expect(fetchMock).toHaveBeenCalledWith(
      "https://api.example.com/v1/capabilities/email.send/resolve",
      expect.objectContaining({ headers: expect.any(Object) })
    );
    expect(result?.providers[0].credentialModes).toEqual(["byok"]);
    expect(result?.providers[0].availableForExecute).toBe(false);
    expect(result?.executeHint?.preferredProvider).toBe("sendgrid");
    expect(result?.executeHint?.unavailableProviderSlugs).toEqual(["resend"]);
    expect(result?.executeHint?.fallbackProviders).toEqual(["amazon-ses"]);
    expect(result?.recoveryHint?.reason).toBe("no_execute_ready_providers");
    expect(result?.recoveryHint?.supportedProviderSlugs).toEqual(["resend", "sendgrid"]);
    expect(result?.recoveryHint?.notExecuteReadyProviderSlugs).toEqual(["postmark"]);
  });
});

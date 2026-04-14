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
            resolve_url: "/v1/capabilities/email.send/resolve",
            credential_modes_url: "/v1/capabilities/email.send/credential-modes",
            supported_provider_slugs: ["resend", "sendgrid"],
            supported_credential_modes: ["agent_vault", "byok"],
            unavailable_provider_slugs: ["resend"],
            not_execute_ready_provider_slugs: ["postmark"],
            alternate_execute_hint: {
              preferred_provider: "sendgrid",
              selection_reason: "higher_ranked_provider_unavailable",
              endpoint_pattern: "POST /v3/mail/send",
              auth_method: "api_key",
              credential_modes: ["byok"],
              configured: true,
              credential_modes_url: "/v1/capabilities/email.send/credential-modes",
              preferred_credential_mode: "byok",
              fallback_providers: ["amazon-ses"],
              setup_hint: null,
              setup_url: null
            }
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
    expect(result?.recoveryHint?.resolveUrl).toBe("/v1/capabilities/email.send/resolve");
    expect(result?.recoveryHint?.supportedProviderSlugs).toEqual(["resend", "sendgrid"]);
    expect(result?.recoveryHint?.notExecuteReadyProviderSlugs).toEqual(["postmark"]);
    expect(result?.recoveryHint?.alternateExecuteHint).toEqual({
      preferredProvider: "sendgrid",
      selectionReason: "higher_ranked_provider_unavailable",
      endpointPattern: "POST /v3/mail/send",
      authMethod: "api_key",
      credentialModes: ["byok"],
      configured: true,
      credentialModesUrl: "/v1/capabilities/email.send/credential-modes",
      preferredCredentialMode: "byok",
      fallbackProviders: ["amazon-ses"],
      setupHint: null,
      setupUrl: null
    });
    expect(result?.recoveryHint?.setupHandoff).toBeNull();
  });

  it("passes credential_mode filters through to /resolve", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        data: {
          capability: "email.send",
          providers: [],
          fallback_chain: [],
          related_bundles: [],
          execute_hint: null,
          recovery_hint: {
            reason: "no_providers_match_credential_mode",
            requested_credential_mode: "agent_vault",
            resolve_url: "/v1/capabilities/email.send/resolve",
            credential_modes_url: "/v1/capabilities/email.send/credential-modes",
            supported_provider_slugs: ["resend", "sendgrid"],
            supported_credential_modes: ["byok", "agent_vault"],
            unavailable_provider_slugs: [],
            not_execute_ready_provider_slugs: [],
            alternate_execute_hint: {
              preferred_provider: "sendgrid",
              selection_reason: "higher_ranked_provider_unavailable",
              endpoint_pattern: "POST /v3/mail/send",
              auth_method: "api_key",
              credential_modes: ["byok"],
              configured: true,
              credential_modes_url: "/v1/capabilities/email.send/credential-modes",
              preferred_credential_mode: "byok",
              fallback_providers: ["amazon-ses"],
              setup_hint: null,
              setup_url: null
            },
            setup_handoff: null
          }
        }
      })
    });
    vi.stubGlobal("fetch", fetchMock);

    const client = createApiClient("https://api.example.com/v1");
    const result = await client.resolveCapability("email.send", { credentialMode: "agent_vault" });

    expect(fetchMock).toHaveBeenCalledWith(
      "https://api.example.com/v1/capabilities/email.send/resolve?credential_mode=agent_vault",
      expect.objectContaining({ headers: expect.any(Object) })
    );
    expect(result?.recoveryHint?.requestedCredentialMode).toBe("agent_vault");
    expect(result?.recoveryHint?.alternateExecuteHint?.preferredCredentialMode).toBe("byok");
  });

  it("parses recovery setup handoff from /resolve", async () => {
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
              circuit_state: "closed"
            }
          ],
          fallback_chain: [],
          related_bundles: [],
          execute_hint: null,
          recovery_hint: {
            reason: "no_execute_ready_providers",
            resolve_url: "/v1/capabilities/email.send/resolve",
            credential_modes_url: "/v1/capabilities/email.send/credential-modes",
            supported_provider_slugs: ["resend"],
            supported_credential_modes: ["byok"],
            unavailable_provider_slugs: [],
            not_execute_ready_provider_slugs: ["resend"],
            setup_handoff: {
              preferred_provider: "resend",
              selection_reason: "highest_ranked_provider",
              auth_method: "api_key",
              configured: false,
              credential_modes: ["byok"],
              credential_modes_url: "/v1/capabilities/email.send/credential-modes",
              preferred_credential_mode: "byok",
              setup_hint: "Set RHUMB_CREDENTIAL_RESEND_API_KEY environment variable or configure via proxy credentials",
              setup_url: "/v1/services/resend/ceremony"
            }
          }
        }
      })
    });
    vi.stubGlobal("fetch", fetchMock);

    const client = createApiClient("https://api.example.com/v1");
    const result = await client.resolveCapability("email.send");

    expect(result?.recoveryHint?.resolveUrl).toBe("/v1/capabilities/email.send/resolve");
    expect(result?.recoveryHint?.alternateExecuteHint).toBeNull();
    expect(result?.recoveryHint?.setupHandoff).toEqual({
      preferredProvider: "resend",
      selectionReason: "highest_ranked_provider",
      endpointPattern: null,
      authMethod: "api_key",
      credentialModes: ["byok"],
      configured: false,
      credentialModesUrl: "/v1/capabilities/email.send/credential-modes",
      preferredCredentialMode: "byok",
      fallbackProviders: [],
      setupHint: "Set RHUMB_CREDENTIAL_RESEND_API_KEY environment variable or configure via proxy credentials",
      setupUrl: "/v1/services/resend/ceremony"
    });
  });

  it("preserves search_url and suggested capabilities when /resolve gets an unknown capability", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      json: async () => ({
        error: "capability_not_found",
        message: "No capability found with id 'Nano Banana Pro'",
        resolution: "Check available capabilities at GET /v1/capabilities or /v1/capabilities?search=...",
        search_url: "/v1/capabilities?search=Nano%20Banana%20Pro",
        suggested_capabilities: [
          {
            id: "ai.generate_image",
            description: "Generate or edit images"
          }
        ]
      })
    });
    vi.stubGlobal("fetch", fetchMock);

    const client = createApiClient("https://api.example.com/v1");
    const result = await client.resolveCapability("Nano Banana Pro");

    expect(result).toEqual({
      capability: "Nano Banana Pro",
      providers: [],
      fallbackChain: [],
      relatedBundles: [],
      executeHint: null,
      recoveryHint: null,
      error: "capability_not_found",
      message: "No capability found with id 'Nano Banana Pro'",
      resolution: "Check available capabilities at GET /v1/capabilities or /v1/capabilities?search=...",
      searchUrl: "/v1/capabilities?search=Nano%20Banana%20Pro",
      suggestedCapabilities: [
        {
          id: "ai.generate_image",
          description: "Generate or edit images"
        }
      ]
    });
  });

  it("canonicalizes legacy byo values across resolve response surfaces", async () => {
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
              credential_modes: ["byo", "byok"],
              configured: false,
              available_for_execute: false,
              circuit_state: "closed"
            }
          ],
          fallback_chain: [],
          related_bundles: [],
          execute_hint: {
            preferred_provider: "resend",
            selection_reason: "highest_ranked_provider",
            auth_method: "api_key",
            credential_modes: ["byo"],
            configured: false,
            credential_modes_url: "/v1/capabilities/email.send/credential-modes",
            preferred_credential_mode: "byo",
            fallback_providers: [],
            setup_hint: "Set RHUMB_CREDENTIAL_RESEND_API_KEY",
            setup_url: "/v1/services/resend/ceremony"
          },
          recovery_hint: {
            reason: "no_execute_ready_providers",
            requested_credential_mode: "byo",
            resolve_url: "/v1/capabilities/email.send/resolve",
            credential_modes_url: "/v1/capabilities/email.send/credential-modes",
            supported_provider_slugs: ["resend"],
            supported_credential_modes: ["byo", "agent_vault"],
            unavailable_provider_slugs: [],
            not_execute_ready_provider_slugs: ["resend"],
            alternate_execute_hint: {
              preferred_provider: "sendgrid",
              selection_reason: "fallback_available",
              auth_method: "api_key",
              credential_modes: ["byo"],
              configured: true,
              credential_modes_url: "/v1/capabilities/email.send/credential-modes",
              preferred_credential_mode: "byo",
              fallback_providers: ["amazon-ses"],
              setup_hint: null,
              setup_url: null
            },
            setup_handoff: {
              preferred_provider: "resend",
              selection_reason: "highest_ranked_provider",
              auth_method: "api_key",
              credential_modes: ["byo"],
              configured: false,
              credential_modes_url: "/v1/capabilities/email.send/credential-modes",
              preferred_credential_mode: "byo",
              fallback_providers: [],
              setup_hint: "Set RHUMB_CREDENTIAL_RESEND_API_KEY",
              setup_url: "/v1/services/resend/ceremony"
            }
          }
        }
      })
    });
    vi.stubGlobal("fetch", fetchMock);

    const client = createApiClient("https://api.example.com/v1");
    const result = await client.resolveCapability("email.send");

    expect(result?.providers[0].credentialModes).toEqual(["byok"]);
    expect(result?.executeHint?.credentialModes).toEqual(["byok"]);
    expect(result?.executeHint?.preferredCredentialMode).toBe("byok");
    expect(result?.recoveryHint?.requestedCredentialMode).toBe("byok");
    expect(result?.recoveryHint?.supportedCredentialModes).toEqual(["byok", "agent_vault"]);
    expect(result?.recoveryHint?.alternateExecuteHint?.credentialModes).toEqual(["byok"]);
    expect(result?.recoveryHint?.alternateExecuteHint?.preferredCredentialMode).toBe("byok");
    expect(result?.recoveryHint?.setupHandoff?.credentialModes).toEqual(["byok"]);
    expect(result?.recoveryHint?.setupHandoff?.preferredCredentialMode).toBe("byok");
  });
});

describe("Rhumb MCP API client execute and estimate", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("canonicalizes legacy byo credential mode in execute and estimate responses", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          data: {
            capability_id: "email.send",
            provider_used: "resend",
            credential_mode: "byo",
            upstream_status: 200,
            upstream_response: { id: "msg_123" },
            cost_estimate_usd: null,
            latency_ms: 42,
            fallback_attempted: false,
            fallback_provider: null,
            execution_id: "exec_123"
          }
        })
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          data: {
            capability_id: "email.send",
            provider: "resend",
            credential_mode: "byo",
            cost_estimate_usd: null,
            circuit_state: "closed",
            endpoint_pattern: "POST /emails",
            execute_readiness: {
              status: "auth_required",
              message: "Add X-Rhumb-Key before execute.",
              resolve_url: "/v1/capabilities/email.send/resolve",
              credential_modes_url: "/v1/capabilities/email.send/credential-modes",
              auth_handoff: {
                reason: "auth_required",
                recommended_path: "governed_api_key",
                retry_url: "/v1/capabilities/email.send/execute",
                docs_url: "/docs#resolve-mental-model",
                paths: [
                  {
                    kind: "governed_api_key",
                    recommended: true,
                    setup_url: "/auth/login",
                    retry_header: "X-Rhumb-Key",
                    summary: "Default for most buyers and most repeat agent traffic.",
                    requires_human_setup: true,
                    automatic_after_setup: true
                  }
                ]
              }
            }
          }
        })
      });
    vi.stubGlobal("fetch", fetchMock);

    const client = createApiClient("https://api.example.com/v1");
    const executeResult = await client.executeCapability("email.send", {
      method: "POST",
      path: "/emails"
    });
    const estimateResult = await client.estimateCapability("email.send");

    expect(executeResult.credentialMode).toBe("byok");
    expect(estimateResult.credentialMode).toBe("byok");
    expect(estimateResult.executeReadiness).toEqual({
      status: "auth_required",
      message: "Add X-Rhumb-Key before execute.",
      resolveUrl: "/v1/capabilities/email.send/resolve",
      credentialModesUrl: "/v1/capabilities/email.send/credential-modes",
      authHandoff: {
        reason: "auth_required",
        recommendedPath: "governed_api_key",
        retryUrl: "/v1/capabilities/email.send/execute",
        docsUrl: "/docs#resolve-mental-model",
        paths: [
          {
            kind: "governed_api_key",
            recommended: true,
            setupUrl: "/auth/login",
            retryHeader: "X-Rhumb-Key",
            summary: "Default for most buyers and most repeat agent traffic.",
            requiresHumanSetup: true,
            automaticAfterSetup: true,
            requiresWalletSupport: null
          }
        ]
      }
    });
  });
});

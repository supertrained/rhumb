import { describe, it, expect, vi } from "vitest";
import { handleCheckCredentials } from "../../src/tools/credentials.js";
import type { RhumbApiClient } from "../../src/api-client.js";

describe("check_credentials", () => {
  it("returns canonical byok mode instead of legacy byo", async () => {
    const client = {
      listManagedCapabilities: vi.fn().mockResolvedValue([]),
      listCeremonies: vi.fn().mockResolvedValue([]),
      getAgentCredentialReadiness: vi.fn().mockResolvedValue(null),
      getCapabilityCredentialModes: vi.fn().mockResolvedValue(null),
    } as unknown as RhumbApiClient;

    const result = await handleCheckCredentials({}, client);

    expect(result.modes[0]).toEqual({
      mode: "byok",
      available: true,
      detail: "Set RHUMB_API_KEY to see your configured BYOK bridges and direct bundles.",
    });
    expect(result.modes.map((mode) => mode.mode)).not.toContain("byo");
  });

  it("surfaces managed capability, ceremony, and agent readiness honestly", async () => {
    const client = {
      listManagedCapabilities: vi.fn().mockResolvedValue([
        {
          capability_id: "email.send",
          service_slug: "resend",
          description: "Send email",
        },
      ]),
      listCeremonies: vi.fn().mockResolvedValue([
        { service_slug: "sendgrid" },
        { service_slug: "mailgun" },
      ]),
      getAgentCredentialReadiness: vi.fn().mockResolvedValue({
        agentId: "agent_123",
        configuredServices: ["resend", "vercel"],
        configuredCount: 2,
        unlockedCapabilities: ["email.send", "deployment.get", "deployment.list"],
        unlockedCount: 3,
        lockedCapabilities: ["payment.charge"],
        lockedCount: 1,
        totalCapabilities: 4,
      }),
      getCapabilityCredentialModes: vi.fn().mockResolvedValue(null),
    } as unknown as RhumbApiClient;

    const result = await handleCheckCredentials({}, client);

    expect(result.modes).toEqual([
      {
        mode: "byok",
        available: true,
        detail: "2 BYOK bridge(s) or direct bundle(s) are already configured: resend, vercel. 3 capability(ies) are ready now, 1 still need setup.",
      },
      {
        mode: "rhumb_managed",
        available: true,
        detail:
          "1 governed Capability(ies) available through Rhumb Resolve. Execution uses X-Rhumb-Key (governed API key or wallet-prefund). No provider API keys needed. Omit credential_mode or use credential_mode=auto to prefer governed execution when available.",
      },
      {
        mode: "agent_vault",
        available: true,
        detail: "2 ceremony guide(s) available. Get your own provider API key following the guide, then pass it per call via the agent_token parameter.",
      },
    ]);

    expect(result.agentReadiness).toEqual({
      configuredServices: ["resend", "vercel"],
      configuredCount: 2,
      unlockedCapabilities: ["email.send", "deployment.get", "deployment.list"],
      unlockedCount: 3,
      lockedCapabilities: ["payment.charge"],
      lockedCount: 1,
      totalCapabilities: 4,
    });
    expect(result.managedCapabilities).toEqual([
      {
        capabilityId: "email.send",
        service: "resend",
        description: "Send email",
      },
    ]);
    expect(result.availableCeremonies).toBe(2);
  });

  it("uses capability-specific credential readiness when a capability is provided", async () => {
    const client = {
      listManagedCapabilities: vi.fn().mockResolvedValue([]),
      listCeremonies: vi.fn().mockResolvedValue([
        { service_slug: "resend" },
      ]),
      getAgentCredentialReadiness: vi.fn().mockResolvedValue(null),
      getCapabilityCredentialModes: vi.fn().mockResolvedValue({
        capabilityId: "email.send",
        providers: [
          {
            serviceSlug: "resend",
            authMethod: "api_key",
            anyConfigured: false,
            modes: [
              {
                mode: "byok",
                available: true,
                configured: false,
                setupHint: "Set RHUMB_CREDENTIAL_RESEND_API_KEY",
              },
              {
                mode: "agent_vault",
                available: true,
                configured: false,
                setupHint: "Use the Resend ceremony",
              },
            ],
          },
          {
            serviceSlug: "rhumb-resend",
            authMethod: "api_key",
            anyConfigured: true,
            modes: [
              {
                mode: "rhumb_managed",
                available: true,
                configured: true,
                setupHint: null,
              },
            ],
          },
        ],
      }),
    } as unknown as RhumbApiClient;

    const result = await handleCheckCredentials({ capability: "email.send" }, client);

    expect(client.getCapabilityCredentialModes).toHaveBeenCalledWith("email.send");
    expect(result.capability).toBe("email.send");
    expect(result.providers).toEqual([
      {
        service: "resend",
        authMethod: "api_key",
        anyConfigured: false,
        modes: [
          {
            mode: "byok",
            available: true,
            configured: false,
            setupHint: "Set RHUMB_CREDENTIAL_RESEND_API_KEY",
            ceremonyAvailable: true,
          },
          {
            mode: "agent_vault",
            available: true,
            configured: false,
            setupHint: "Use the Resend ceremony",
            ceremonyAvailable: true,
          },
        ],
      },
      {
        service: "rhumb-resend",
        authMethod: "api_key",
        anyConfigured: true,
        modes: [
          {
            mode: "rhumb_managed",
            available: true,
            configured: true,
            setupHint: null,
            ceremonyAvailable: false,
          },
        ],
      },
    ]);
    expect(result.modes).toEqual([
      {
        mode: "byok",
        available: true,
        detail: "BYOK is supported by resend; follow the provider setup hint to unlock it.",
      },
      {
        mode: "rhumb_managed",
        available: true,
        detail:
          "Governed execution (X-Rhumb-Key) is available through rhumb-resend. No provider API key required for those providers.",
      },
      {
        mode: "agent_vault",
        available: true,
        detail: "Ceremony-guided setup is available for resend.",
      },
    ]);
  });

  it("does not overstate BYOK when capability readiness fails to load", async () => {
    const client = {
      listManagedCapabilities: vi.fn().mockResolvedValue([]),
      listCeremonies: vi.fn().mockResolvedValue([]),
      getAgentCredentialReadiness: vi.fn().mockResolvedValue(null),
      getCapabilityCredentialModes: vi.fn().mockResolvedValue(null),
    } as unknown as RhumbApiClient;

    const result = await handleCheckCredentials({ capability: "email.send" }, client);

    expect(result.error).toContain("Couldn't load credential-mode readiness");
    expect(result.modes[0].mode).toBe("byok");
    expect(result.modes[0].detail).toContain("Credential readiness did not load");
    expect(result.modes[0].detail).not.toContain("default fallback rail");
  });
});

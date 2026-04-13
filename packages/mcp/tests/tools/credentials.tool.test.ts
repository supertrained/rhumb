import { describe, it, expect, vi } from "vitest";
import { handleCheckCredentials } from "../../src/tools/credentials.js";
import type { RhumbApiClient } from "../../src/api-client.js";

describe("check_credentials", () => {
  it("returns canonical byok mode instead of legacy byo", async () => {
    const client = {
      listManagedCapabilities: vi.fn().mockResolvedValue([]),
      listCeremonies: vi.fn().mockResolvedValue([]),
    } as unknown as RhumbApiClient;

    const result = await handleCheckCredentials({}, client);

    expect(result.modes[0]).toEqual({
      mode: "byok",
      available: true,
      detail: "BYOK. Set RHUMB_API_KEY env var and pass credentials via the call.",
    });
    expect(result.modes.map((mode) => mode.mode)).not.toContain("byo");
  });

  it("surfaces managed capability and ceremony availability honestly", async () => {
    const client = {
      listManagedCapabilities: vi.fn().mockResolvedValue([
        {
          capability_id: "email.send",
          service_slug: "resend",
          description: "Send email",
        },
      ]),
      listCeremonies: vi.fn().mockResolvedValue([
        { service: "sendgrid" },
        { service: "mailgun" },
      ]),
    } as unknown as RhumbApiClient;

    const result = await handleCheckCredentials({}, client);

    expect(result.modes).toEqual([
      {
        mode: "byok",
        available: true,
        detail: "BYOK. Set RHUMB_API_KEY env var and pass credentials via the call.",
      },
      {
        mode: "rhumb_managed",
        available: true,
        detail: "1 zero-config Capability(ies) available through Rhumb Resolve. No credentials needed — omit credential_mode or use credential_mode=auto to prefer Rhumb Resolve when available.",
      },
      {
        mode: "agent_vault",
        available: true,
        detail: "2 ceremony guide(s) available. Get your own API key following the guide, then pass it per call via the agent_token parameter.",
      },
    ]);

    expect(result.managedCapabilities).toEqual([
      {
        capabilityId: "email.send",
        service: "resend",
        description: "Send email",
      },
    ]);
    expect(result.availableCeremonies).toBe(2);
  });
});

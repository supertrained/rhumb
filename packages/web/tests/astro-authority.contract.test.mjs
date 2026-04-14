import { readFileSync } from "node:fs";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const ROOT_LLMS = readFileSync(new URL("../../../llms.txt", import.meta.url), "utf8");
const ROOT_MANIFEST = JSON.parse(
  readFileSync(new URL("../../../agent-capabilities.json", import.meta.url), "utf8")
);
const ASTRO_PUBLIC_MANIFEST = JSON.parse(
  readFileSync(new URL("../../astro-web/public/.well-known/agent-capabilities.json", import.meta.url), "utf8")
);

vi.mock("../../astro-web/src/lib/api.ts", () => ({
  getServices: vi.fn(async () => [
    { slug: "stripe", name: "Stripe", description: "Payments API", category: "payments" },
  ]),
  getCategories: vi.fn(async () => [
    { slug: "payments", serviceCount: 1 },
  ]),
}));

describe("astro authority contract", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(JSON.stringify({ data: { total: 415 } }), {
          status: 200,
          headers: { "Content-Type": "application/json; charset=utf-8" },
        })
      )
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.resetModules();
  });

  it("serves the live Astro llms route with explicit recovery_hint field names", async () => {
    const mod = await import("../../astro-web/src/pages/llms.txt.ts");
    const res = await mod.GET({});
    const body = await res.text();

    expect(res.headers.get("Content-Type")).toBe("text/plain; charset=utf-8");
    expect(body).toContain("resolve_capability");
    expect(body).toContain("recovery_hint.resolve_url");
    expect(body).toContain("recovery_hint.credential_modes_url");
    expect(body).toContain("recovery_hint.alternate_execute_hint");
    expect(body).toContain("recovery_hint.setup_handoff");
    expect(body).not.toContain("machine-readable recovery handoffs");
    expect(body).not.toContain("follow recovery handoffs when a filtered route dead-ends");
  });

  it("keeps the Astro public agent-capabilities surface aligned with the canonical manifest", () => {
    const resolveTool = ASTRO_PUBLIC_MANIFEST.capabilities.discovery.tools.find(
      (tool) => tool.name === "resolve_capability"
    );

    expect(ASTRO_PUBLIC_MANIFEST).toEqual(ROOT_MANIFEST);
    expect(resolveTool?.description).toContain("recovery_hint.resolve_url");
    expect(resolveTool?.description).toContain("recovery_hint.credential_modes_url");
    expect(resolveTool?.description).toContain("recovery_hint.alternate_execute_hint");
    expect(resolveTool?.description).toContain("recovery_hint.setup_handoff");
    expect(resolveTool?.description).not.toContain("machine-readable recovery handoffs");
  });

  it("keeps the Astro llms route aligned with the canonical recovery-field wording", async () => {
    const mod = await import("../../astro-web/src/pages/llms.txt.ts");
    const res = await mod.GET({});
    const body = await res.text();

    expect(ROOT_LLMS).toContain("recovery_hint.resolve_url");
    expect(ROOT_LLMS).toContain("recovery_hint.credential_modes_url");
    expect(ROOT_LLMS).toContain("recovery_hint.alternate_execute_hint");
    expect(ROOT_LLMS).toContain("recovery_hint.setup_handoff");
    expect(body).toContain("recovery_hint.resolve_url");
    expect(body).toContain("recovery_hint.credential_modes_url");
    expect(body).toContain("recovery_hint.alternate_execute_hint");
    expect(body).toContain("recovery_hint.setup_handoff");
  });
});

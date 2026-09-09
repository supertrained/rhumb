import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const ROOT_LLMS = readFileSync(new URL("../../../llms.txt", import.meta.url), "utf8");
const ASTRO_LLMS_ROUTE = readFileSync(
  new URL("../../astro-web/src/pages/llms.txt.ts", import.meta.url),
  "utf8"
);
const ROOT_MANIFEST = JSON.parse(
  readFileSync(new URL("../../../agent-capabilities.json", import.meta.url), "utf8")
);
const ASTRO_PUBLIC_MANIFEST = JSON.parse(
  readFileSync(new URL("../../astro-web/public/.well-known/agent-capabilities.json", import.meta.url), "utf8")
);
const ASTRO_ROOT_MANIFEST = JSON.parse(
  readFileSync(new URL("../../astro-web/public/agent-capabilities.json", import.meta.url), "utf8")
);

describe("astro authority contract", () => {
  it("keeps the Astro llms route source aligned with explicit recovery_hint field names", () => {
    expect(ASTRO_LLMS_ROUTE).toContain("resolve_capability");
    expect(ASTRO_LLMS_ROUTE).toContain("recovery_hint.resolve_url");
    expect(ASTRO_LLMS_ROUTE).toContain("recovery_hint.credential_modes_url");
    expect(ASTRO_LLMS_ROUTE).toContain("recovery_hint.alternate_execute_hint");
    expect(ASTRO_LLMS_ROUTE).toContain("recovery_hint.setup_handoff");
    expect(ASTRO_LLMS_ROUTE).not.toContain("machine-readable recovery handoffs");
    expect(ASTRO_LLMS_ROUTE).not.toContain("follow recovery handoffs when a filtered route dead-ends");
  });

  it("keeps the Astro public agent-capabilities surface aligned with the canonical manifest", () => {
    const resolveTool = ASTRO_PUBLIC_MANIFEST.capabilities.discovery.tools.find(
      (tool) => tool.name === "resolve_capability"
    );

    expect(ASTRO_PUBLIC_MANIFEST).toEqual(ROOT_MANIFEST);
    expect(ASTRO_ROOT_MANIFEST).toEqual(ROOT_MANIFEST);
    expect(resolveTool?.description).toContain("recovery_hint.resolve_url");
    expect(resolveTool?.description).toContain("recovery_hint.credential_modes_url");
    expect(resolveTool?.description).toContain("recovery_hint.alternate_execute_hint");
    expect(resolveTool?.description).toContain("recovery_hint.setup_handoff");
    expect(resolveTool?.description).not.toContain("machine-readable recovery handoffs");
  });

  it("keeps the Astro llms route aligned with the canonical recovery-field wording", () => {
    expect(ROOT_LLMS).toContain("recovery_hint.resolve_url");
    expect(ROOT_LLMS).toContain("recovery_hint.credential_modes_url");
    expect(ROOT_LLMS).toContain("recovery_hint.alternate_execute_hint");
    expect(ROOT_LLMS).toContain("recovery_hint.setup_handoff");
    expect(ASTRO_LLMS_ROUTE).toContain("recovery_hint.resolve_url");
    expect(ASTRO_LLMS_ROUTE).toContain("recovery_hint.credential_modes_url");
    expect(ASTRO_LLMS_ROUTE).toContain("recovery_hint.alternate_execute_hint");
    expect(ASTRO_LLMS_ROUTE).toContain("recovery_hint.setup_handoff");
  });
});

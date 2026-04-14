import { readFileSync } from "node:fs";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

const failureModesSource = readFileSync(
  new URL("../../astro-web/src/pages/docs/failure-modes.astro", import.meta.url),
  "utf8",
);
const astroDocsSource = readFileSync(new URL("../../astro-web/src/pages/docs.astro", import.meta.url), "utf8");
const astroGettingStartedSource = readFileSync(
  new URL("../../astro-web/src/pages/blog/getting-started-mcp.astro", import.meta.url),
  "utf8",
);
const mcpQuickstartSource = readFileSync(
  new URL("../../../examples/mcp-quickstart.md", import.meta.url),
  "utf8",
);
const apiDocSource = readFileSync(new URL("../../../docs/API.md", import.meta.url), "utf8");

(globalThis as typeof globalThis & { React: typeof React }).React = React;

async function renderDocsPage(): Promise<string> {
  const module = await import("../app/docs/page");
  const page = await module.default();
  return renderToStaticMarkup(page);
}

describe("docs page", () => {
  it("renders the current MCP tool surface and resolve handoff guidance", async () => {
    const html = await renderDocsPage();

    expect(html).toContain("resolve_capability");
    expect(html).toContain("credential-mode filtering");
    expect(html).toContain("machine-readable recovery fields");
    expect(html).toContain("recovery_hint.resolve_url");
    expect(html).toContain("recovery_hint.credential_modes_url");
    expect(html).toContain("recovery_hint.alternate_execute_hint");
    expect(html).toContain("recovery_hint.setup_handoff");
    expect(html).toContain("search suggestions when the capability ID is wrong");
    expect(html).toContain("estimate_capability");
    expect(html).toContain("Estimate the active execution rail, cost, and health before execution.");
    expect(html).toContain("machine-readable execute_readiness handoffs");
    expect(html).toContain("check_credentials");
    expect(html).toContain("rhumb_list_recipes");
    expect(html).toContain("get_receipt");

    expect(html).not.toContain("estimate_cost");
    expect(html).not.toContain("get_credentials");
    expect(html).not.toContain("search_services");
    expect(html).not.toContain("get_ceremonies");
  });

  it("keeps the failure-modes guidance aligned with resolve recovery handoffs", () => {
    expect(failureModesSource).toContain("machine-readable recovery fields");
    expect(failureModesSource).toContain("recovery_hint.resolve_url");
    expect(failureModesSource).toContain("recovery_hint.credential_modes_url");
    expect(failureModesSource).toContain("alternate_execute_hint");
    expect(failureModesSource).toContain("setup_handoff");
    expect(failureModesSource).not.toContain("Build routing fallback chains: primary → alternative → manual.");
  });

  it("keeps the MCP quickstart estimate guidance aligned with the live preflight contract", () => {
    expect(mcpQuickstartSource).toContain(
      'What execution rail, health, and cost should I expect before this call runs?',
    );
    expect(mcpQuickstartSource).toContain(
      "check the active execution rail, health, and cost before execution",
    );
    expect(mcpQuickstartSource).toContain("recovery_hint.resolve_url");
    expect(mcpQuickstartSource).toContain("recovery_hint.credential_modes_url");
    expect(mcpQuickstartSource).toContain("recovery_hint.alternate_execute_hint");
    expect(mcpQuickstartSource).toContain("recovery_hint.setup_handoff");
    expect(mcpQuickstartSource).not.toContain("recovery handoffs");
    expect(mcpQuickstartSource).not.toContain('`estimate_capability` — "How much will this call cost?"');
    expect(mcpQuickstartSource).not.toContain("`estimate_capability` — check cost before paying");
  });

  it("keeps the owned API docs aligned with explicit recovery_hint field names", () => {
    expect(apiDocSource).toContain("recovery_hint.resolve_url");
    expect(apiDocSource).toContain("recovery_hint.credential_modes_url");
    expect(apiDocSource).toContain("recovery_hint.alternate_execute_hint");
    expect(apiDocSource).toContain("recovery_hint.setup_handoff");
    expect(apiDocSource).toContain("retry with `X-Payment` carrying `tx_hash`, `network`, and `wallet_address`");
    expect(apiDocSource).toContain("wrapped authorization payloads, use wallet-prefund instead of the direct per-call retry");
    expect(apiDocSource).not.toContain("Use `alternate_execute_hint` when");
    expect(apiDocSource).not.toContain("plus `resolve_url` and `credential_modes_url`");
  });

  it("keeps the hand-written Astro docs surfaces aligned with the full recovery_hint field set", () => {
    for (const source of [astroDocsSource, astroGettingStartedSource]) {
      expect(source).toContain("recovery_hint.resolve_url");
      expect(source).toContain("recovery_hint.credential_modes_url");
      expect(source).toContain("recovery_hint.alternate_execute_hint");
      expect(source).toContain("recovery_hint.setup_handoff");
    }

    expect(astroDocsSource).not.toContain("recovery_hint.resolve_url and recovery_hint.setup_handoff");
    expect(astroGettingStartedSource).not.toContain("recovery_hint.resolve_url and recovery_hint.setup_handoff");
  });
});

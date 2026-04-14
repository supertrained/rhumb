import { readFileSync } from "node:fs";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

const failureModesSource = readFileSync(
  new URL("../../astro-web/src/pages/docs/failure-modes.astro", import.meta.url),
  "utf8",
);
const mcpQuickstartSource = readFileSync(
  new URL("../../../examples/mcp-quickstart.md", import.meta.url),
  "utf8",
);

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
    expect(html).toContain("machine-readable recovery handoffs");
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
    expect(failureModesSource).toContain("machine-readable recovery handoffs");
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
    expect(mcpQuickstartSource).not.toContain('`estimate_capability` — "How much will this call cost?"');
    expect(mcpQuickstartSource).not.toContain("`estimate_capability` — check cost before paying");
  });
});

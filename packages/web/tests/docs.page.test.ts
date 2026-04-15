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
    expect(html).toContain("Inspect live credential-mode readiness, globally or for a specific Capability.");
    expect(html).toContain("rhumb_list_recipes");
    expect(html).toContain("get_receipt");
    expect(html).toContain("92 scored categories");
    expect(html).toContain("the ranked leaderboard hub currently covers 11 categories");
    expect(html).toContain("Execution requires a live rail");
    expect(html).toContain("governed API key, wallet-prefund, or x402 per-call rails");
    expect(html).toContain("Bring BYOK or Agent Vault when provider control is the point");
    expect(html).toContain("rank providers and surface machine-readable recovery fields");
    expect(html).toContain("inspect live readiness globally or for a specific Capability before choosing a rail");
    expect(html).toContain("Before you wire these routes into production");
    expect(html).toContain("Trust →");
    expect(html).toContain("Methodology →");
    expect(html).toContain("Dispute a score →");
    expect(html).toContain("/providers#dispute-a-score");

    expect(html).not.toContain("requires an API key or x402 payment");
    expect(html).not.toContain("governed API key, wallet-prefund, x402 per-call, or BYOK");
    expect(html).not.toContain("92 categories — browse all at");
    expect(html).not.toContain("to inspect the available credential modes");
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
    expect(failureModesSource).toContain("All execution paths (Rhumb-managed, Agent Vault, BYOK, x402)");
    expect(failureModesSource).toContain("Governed API key and wallet-prefund billing paths only. x402, BYOK, and Agent Vault are unaffected.");
    expect(failureModesSource).toContain("Rhumb-managed execution only. Agent Vault, BYOK, and x402 are unaffected.");
    expect(failureModesSource).toContain("provide a valid governed API key");
    expect(failureModesSource).not.toContain("Build routing fallback chains: primary → alternative → manual.");
    expect(failureModesSource).not.toContain("All modes (Managed, x402, BYOK)");
    expect(failureModesSource).not.toContain("Managed billing (Mode 2) executions only. x402 and BYOK continue working because they don't depend on Rhumb's billing database.");
    expect(failureModesSource).not.toContain("All managed execution (Mode 2). BYOK and x402 continue working.");
    expect(failureModesSource).not.toContain("provide a valid API key");
  });

  it("keeps the MCP quickstart estimate guidance aligned with the live preflight contract", () => {
    expect(mcpQuickstartSource).toContain(
      'What execution rail, health, and cost should I expect before this call runs?',
    );
    expect(mcpQuickstartSource).toContain(
      "check the active execution rail, health, and cost before execution",
    );
    expect(mcpQuickstartSource).toContain("### Without a governed API key (free, no signup)");
    expect(mcpQuickstartSource).toContain("### With a governed API key (default production path)");
    expect(mcpQuickstartSource).toContain("recovery_hint.resolve_url");
    expect(mcpQuickstartSource).toContain("recovery_hint.credential_modes_url");
    expect(mcpQuickstartSource).toContain("recovery_hint.alternate_execute_hint");
    expect(mcpQuickstartSource).toContain("recovery_hint.setup_handoff");
    expect(mcpQuickstartSource).not.toContain("recovery handoffs");
    expect(mcpQuickstartSource).not.toContain('`estimate_capability` — "How much will this call cost?"');
    expect(mcpQuickstartSource).not.toContain("`estimate_capability` — check cost before paying");
    expect(mcpQuickstartSource).not.toContain("### Without an API key (free, no signup)");
    expect(mcpQuickstartSource).not.toContain("### With an API key (default production path)");
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
      expect(source).toContain("Inspect live credential-mode readiness, globally or for a specific Capability");
      expect(source).not.toContain("which credential modes are available to you");
    }

    expect(astroDocsSource).toContain("governed API key, wallet-prefund, or x402 per-call where supported");
    expect(astroDocsSource).toContain("provider-controlled paths through BYOK or Agent Vault");
    expect(astroDocsSource).not.toContain("governed API key, wallet-prefund, BYOK, or x402 where supported");
    expect(astroDocsSource).not.toContain("recovery_hint.resolve_url and recovery_hint.setup_handoff");
    expect(astroGettingStartedSource).not.toContain("recovery_hint.resolve_url and recovery_hint.setup_handoff");
  });
});

import { readFileSync } from "node:fs";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

(globalThis as typeof globalThis & { React: typeof React }).React = React;

const pricingPageSource = readFileSync(new URL("../app/pricing/page.tsx", import.meta.url), "utf8");
const astroPricingSource = readFileSync(
  new URL("../../astro-web/src/pages/pricing.astro", import.meta.url),
  "utf8",
);

async function renderPricingPage(): Promise<string> {
  const module = await import("../app/pricing/page");
  const page = await module.default();
  return renderToStaticMarkup(page);
}

describe("pricing page", () => {
  it("keeps pricing metadata aligned with rail and provider-control truth", () => {
    expect(pricingPageSource).toContain("governed API key, wallet-prefund, or x402 per-call rails");
    expect(pricingPageSource).toContain("BYOK or Agent Vault when provider control is the point");
    expect(pricingPageSource).toContain("BYOK and Agent Vault provider-control modes");
    expect(pricingPageSource).not.toContain("Choose governed API key, wallet-prefund, x402 per-call, or BYOK");
    expect(pricingPageSource).not.toContain("x402 per-call, and BYOK paths");
  });

  it("renders the current estimate handoff truth for agents", async () => {
    const html = await renderPricingPage();

    expect(html).toContain("estimate_capability");
    expect(html).toContain("active execution rail");
    expect(html).toContain("health, and exact cost");
    expect(html).toContain("machine-readable");
    expect(html).toContain("execute_readiness");
    expect(html).toContain("Anonymous direct system-of-record");

    expect(html).not.toContain("Estimate cost before execution");
    expect(html).not.toContain("will cost before you run it");
  });

  it("aligns the public rail chooser with current pricing truth", async () => {
    const html = await renderPricingPage();

    expect(html).toContain("Governed API key");
    expect(html).toContain("Wallet-prefund");
    expect(html).toContain("x402 per-call");
    expect(html).toContain("BYOK or Agent Vault");
    expect(html).toContain("Agent Vault");
    expect(html).toContain("No subscriptions, no seat fees, no minimums");
    expect(html).toContain("Adds a funding step before the steady-state execute path.");
    expect(html).toContain("If your buyer emits wrapped proofs instead of the supported tx-hash flow, switch to wallet-prefund.");
    expect(html).toContain("Before you choose a payment rail");
    expect(html).toContain("Trust →");
    expect(html).toContain("Methodology →");
    expect(html).toContain("Dispute a score →");
    expect(html).toContain("/providers#dispute-a-score");

    expect(html).not.toContain("Minimum top-up");
    expect(html).not.toContain("Two payment rails");
  });

  it("keeps the provider-control chooser aligned with explicit resolve recovery fields", async () => {
    const html = await renderPricingPage();

    expect(html).toContain("resolve_capability with credential_mode=byok");
    expect(html).toContain("credential_mode=agent_vault");
    expect(html).toContain("Agent Vault");
    expect(html).toContain("recovery_hint.resolve_url");
    expect(html).toContain("recovery_hint.credential_modes_url");
    expect(html).toContain("recovery_hint.alternate_execute_hint");
    expect(html).toContain("recovery_hint.setup_handoff");

    expect(html).not.toContain("machine-readable setup or recovery handoff");
  });

  it("keeps the Astro pricing surface aligned with current chooser and resolve recovery truth", () => {
    expect(astroPricingSource).toContain("tradeoff: \"Adds a funding step before the steady-state execute path.\"");
    expect(astroPricingSource).toContain('cta: "Start with governed API key"');
    expect(astroPricingSource).toContain("If your buyer emits wrapped proofs instead of the supported tx-hash flow, switch to wallet-prefund.");
    expect(astroPricingSource).toContain("whether you want a governed rail (governed API key or wallet-prefund), zero-signup x402 per-call, or provider-controlled paths like BYOK or Agent Vault.");
    expect(astroPricingSource).toContain("name: \"BYOK or Agent Vault\"");
    expect(astroPricingSource).toContain("Provider control");
    expect(astroPricingSource).toContain("BYOK / Vault");
    expect(astroPricingSource).toContain('>Governed API key</h3>');
    expect(astroPricingSource).toContain("Agent Vault setup");
    expect(astroPricingSource).toContain('q: "What is the difference between governed API key, wallet-prefund, and x402?"');
    expect(astroPricingSource).toContain("Governed API key and wallet-prefund both execute with X-Rhumb-Key. Governed API key is account-first billing;");
    expect(astroPricingSource).toContain("governed API-key path, BYOK, or Agent Vault");
    expect(astroPricingSource).toContain("Already have provider credentials? BYOK or Agent Vault routes through Rhumb at zero");
    expect(astroPricingSource).toContain("agent_vault");
    expect(astroPricingSource).toContain("resolve_capability");
    expect(astroPricingSource).toContain("recovery_hint.resolve_url");
    expect(astroPricingSource).toContain("recovery_hint.credential_modes_url");
    expect(astroPricingSource).toContain("recovery_hint.alternate_execute_hint");
    expect(astroPricingSource).toContain("recovery_hint.setup_handoff");
    expect(astroPricingSource).toContain("wallet-prefund, or x402 per-call settlement");
    expect(astroPricingSource).toContain("account billing with governed API keys,");
    expect(astroPricingSource).toContain("Rhumb handles routing, failover, and billing on the governed API key rail.");
    expect(astroPricingSource).toContain('>Wallet-prefund</td>');
    expect(astroPricingSource).toContain("For wallet-first flows (x402 per-call and wallet-prefund), see our");
    expect(astroPricingSource).toContain('Create a governed API key for standard pricing');
    expect(astroPricingSource).toContain('Get governed API key');

    expect(astroPricingSource).not.toContain("Has a setup step before the first repeatable execution path.");
    expect(astroPricingSource).not.toContain('cta: "Start with API key"');
    expect(astroPricingSource).not.toContain("account API key, wallet-prefunded balance, zero-signup x402 per-call, or BYOK passthrough.");
    expect(astroPricingSource).not.toContain('q: "What is the difference between API key, wallet-prefund, and x402?"');
    expect(astroPricingSource).not.toContain("API key and wallet-prefund both execute with X-Rhumb-Key. API key is account-first billing;");
    expect(astroPricingSource).not.toContain("whether you want a governed rail (API key or wallet-prefund), zero-signup x402 per-call, or provider-controlled paths like BYOK or Agent Vault.");
    expect(astroPricingSource).not.toContain('>API key</h3>');
    expect(astroPricingSource).not.toContain("account billing with API keys,");
    expect(astroPricingSource).not.toContain("wallet-prefunded balance");
    expect(astroPricingSource).not.toContain('Create an API key for standard pricing');
    expect(astroPricingSource).not.toContain('Get API key');
    expect(astroPricingSource).not.toContain("Already have provider API keys? BYOK passthrough routes through Rhumb at zero");
    expect(astroPricingSource).not.toContain("Rhumb handles routing, failover, and billing behind one key.");
    expect(astroPricingSource).not.toContain(
      '<p class="text-sm leading-6 text-slate-400">Route through Rhumb with your own provider credentials when you need direct vendor control or enterprise boundaries.</p>',
    );
  });
});

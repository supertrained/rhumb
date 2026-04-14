import { readFileSync } from "node:fs";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

(globalThis as typeof globalThis & { React: typeof React }).React = React;

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
    expect(html).toContain("BYOK");
    expect(html).toContain("No subscriptions, no seat fees, no minimums");

    expect(html).not.toContain("Minimum top-up");
    expect(html).not.toContain("Two payment rails");
  });

  it("keeps the BYOK rail chooser aligned with explicit resolve recovery fields", async () => {
    const html = await renderPricingPage();

    expect(html).toContain("resolve_capability with credential_mode=byok");
    expect(html).toContain("recovery_hint.resolve_url");
    expect(html).toContain("recovery_hint.credential_modes_url");
    expect(html).toContain("recovery_hint.alternate_execute_hint");
    expect(html).toContain("recovery_hint.setup_handoff");

    expect(html).not.toContain("machine-readable setup or recovery handoff");
  });

  it("keeps the Astro pricing BYOK surface aligned with explicit resolve recovery fields", () => {
    expect(astroPricingSource).toContain("resolve_capability");
    expect(astroPricingSource).toContain("recovery_hint.resolve_url");
    expect(astroPricingSource).toContain("recovery_hint.credential_modes_url");
    expect(astroPricingSource).toContain("recovery_hint.alternate_execute_hint");
    expect(astroPricingSource).toContain("recovery_hint.setup_handoff");

    expect(astroPricingSource).not.toContain(
      '<p class="text-sm leading-6 text-slate-400">Route through Rhumb with your own provider credentials when you need direct vendor control or enterprise boundaries.</p>',
    );
  });
});

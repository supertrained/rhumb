import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const layout = readFileSync(new URL("../app/layout.tsx", import.meta.url), "utf8");
const terms = readFileSync(new URL("../../astro-web/src/pages/terms.astro", import.meta.url), "utf8");
const glossary = readFileSync(new URL("../../astro-web/src/pages/glossary.astro", import.meta.url), "utf8");
const rootLlms = readFileSync(new URL("../../../llms.txt", import.meta.url), "utf8");
const webPublicLlms = readFileSync(new URL("../public/llms.txt", import.meta.url), "utf8");

describe("public authority pricing contract", () => {
  it("keeps the sitewide web metadata aligned with current pricing truth", () => {
    expect(layout).toContain("npx rhumb-mcp@latest");
    expect(layout).toContain("wallet-prefund");
    expect(layout).toContain("BYOK");
    expect(layout).toContain("Discovery, scoring, and browsing are free");

    expect(layout).not.toContain("Free tier: 1,000 executions/month");
    expect(layout).not.toContain('"ai:free-tier": "1000 executions/month"');
    expect(layout).not.toContain('name: "Free Tier"');
    expect(layout).not.toContain("npx rhumb-mcp@0.6.0");
  });

  it("removes stale free-tier and split-markup claims from legal and glossary surfaces", () => {
    expect(terms).toContain("wallet-prefund");
    expect(terms).toContain("BYOK");
    expect(terms).toContain("current pricing and markup terms are published");
    expect(terms).not.toContain("A free tier provides 1,000 calls per month");
    expect(terms).not.toContain("15% for x402/USDC");

    expect(glossary).toContain("wallet-prefund");
    expect(glossary).toContain("Discovery is free, and execution pricing lives on /pricing.");
    expect(glossary).not.toContain("public free tier includes 1,000 calls per month");
  });

  it("keeps llms discovery surfaces aligned with live rail-based pricing truth", () => {
    expect(rootLlms).toContain("wallet-prefund");
    expect(rootLlms).toContain("No subscriptions, no seat fees, no minimums");
    expect(rootLlms).toContain("Live pricing and markup terms: https://rhumb.dev/pricing");
    expect(rootLlms).not.toContain("Free tier: 1,000 calls/month");

    expect(webPublicLlms).toContain("wallet-prefund");
    expect(webPublicLlms).toContain("No subscriptions, no seat fees, no minimums");
    expect(webPublicLlms).toContain("Live pricing and markup terms: https://rhumb.dev/pricing");
    expect(webPublicLlms).not.toContain("Free tier: 1,000 calls/month");

    expect(webPublicLlms).toBe(rootLlms);
  });
});

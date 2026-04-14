import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const layout = readFileSync(new URL("../app/layout.tsx", import.meta.url), "utf8");
const webHome = readFileSync(new URL("../app/page.tsx", import.meta.url), "utf8");
const webAbout = readFileSync(new URL("../app/about/page.tsx", import.meta.url), "utf8");
const webBlogAag = readFileSync(new URL("../app/blog/aag-framework/page.tsx", import.meta.url), "utf8");
const webBlogHowToEvaluate = readFileSync(new URL("../app/blog/how-to-evaluate-apis-for-agents/page.tsx", import.meta.url), "utf8");
const webBlogPayments = readFileSync(new URL("../app/blog/payments-for-agents/page.tsx", import.meta.url), "utf8");
const webBlogSelfScore = readFileSync(new URL("../app/blog/self-score/page.tsx", import.meta.url), "utf8");
const webLeaderboard = readFileSync(new URL("../app/leaderboard/page.tsx", import.meta.url), "utf8");
const webSearch = readFileSync(new URL("../app/search/page.tsx", import.meta.url), "utf8");
const webPublicTruth = readFileSync(new URL("../lib/public-truth.ts", import.meta.url), "utf8");
const terms = readFileSync(new URL("../../astro-web/src/pages/terms.astro", import.meta.url), "utf8");
const glossary = readFileSync(new URL("../../astro-web/src/pages/glossary.astro", import.meta.url), "utf8");
const astroAbout = readFileSync(new URL("../../astro-web/src/pages/about.astro", import.meta.url), "utf8");
const astroBlogIndex = readFileSync(new URL("../../astro-web/src/pages/blog/index.astro", import.meta.url), "utf8");
const astroDocs = readFileSync(new URL("../../astro-web/src/pages/docs.astro", import.meta.url), "utf8");
const astroHome = readFileSync(new URL("../../astro-web/src/pages/index.astro", import.meta.url), "utf8");
const astroLeaderboardHub = readFileSync(new URL("../../astro-web/src/pages/leaderboard/index.astro", import.meta.url), "utf8");
const astroHowToEvaluate = readFileSync(new URL("../../astro-web/src/pages/blog/how-to-evaluate-apis-for-agents.astro", import.meta.url), "utf8");
const astroMultiProviderMcp = readFileSync(new URL("../../astro-web/src/pages/blog/what-nobody-tells-you-building-multi-provider-mcp-server.astro", import.meta.url), "utf8");
const astroWallets = readFileSync(new URL("../../astro-web/src/pages/blog/why-agent-wallets-keep-losing-money.astro", import.meta.url), "utf8");
const astroLlmsRoute = readFileSync(new URL("../../astro-web/src/pages/llms.txt.ts", import.meta.url), "utf8");
const astroSearch = readFileSync(new URL("../../astro-web/src/pages/search.astro", import.meta.url), "utf8");
const astroSecurity = readFileSync(new URL("../../astro-web/src/pages/security.astro", import.meta.url), "utf8");
const astroCapabilities = readFileSync(new URL("../../astro-web/src/pages/capabilities.astro", import.meta.url), "utf8");
const rootLlms = readFileSync(new URL("../../../llms.txt", import.meta.url), "utf8");
const webPublicLlms = readFileSync(new URL("../public/llms.txt", import.meta.url), "utf8");
const apiDocs = readFileSync(new URL("../../../docs/API.md", import.meta.url), "utf8");
const canonicalPricing = JSON.parse(
  readFileSync(new URL("../../shared/pricing.json", import.meta.url), "utf8"),
);
const rootAgentCapabilities = readFileSync(
  new URL("../../../agent-capabilities.json", import.meta.url),
  "utf8",
);
const wellKnownAgentCapabilities = readFileSync(
  new URL("../../astro-web/public/.well-known/agent-capabilities.json", import.meta.url),
  "utf8",
);

function extractPricingExampleJson(markdown: string) {
  const match = markdown.match(
    /### `GET \/v1\/pricing`[\s\S]*?```json\n([\s\S]*?)\n```/,
  );
  expect(match).not.toBeNull();
  return JSON.parse(match![1]);
}

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

  it("keeps the astro docs authority surface pinned to canonical public truth", () => {
    expect(astroDocs).toContain('const servicesLabel = PUBLIC_TRUTH.servicesLabel;');
    expect(astroDocs).toContain('Search ${servicesLabel} scored services');
    expect(astroDocs).not.toContain('getServiceCount');
  });

  it("keeps the astro homepage authority surface pinned to canonical public truth", () => {
    expect(astroHome).toContain('const servicesLabel = PUBLIC_TRUTH.servicesLabel;');
    expect(astroHome).toContain('Search ${servicesLabel} services');
    expect(astroHome).toContain('Search ${servicesLabel} scored services');
    expect(astroHome).not.toContain('getServiceCount');
  });

  it("keeps the web homepage, about, and search authority surfaces pinned to public truth labels", () => {
    expect(webPublicTruth).toContain('servicesLabel: "1,038"');
    expect(webPublicTruth).toContain('categoriesLabel: "92"');

    expect(webHome).toContain('PUBLIC_TRUTH.servicesLabel');
    expect(webHome).toContain('PUBLIC_TRUTH.categoriesLabel');
    expect(webHome).not.toContain('getServiceCount');
    expect(webHome).not.toContain('{ value: "11", label: "categories" }');

    expect(webAbout).toContain('import { PUBLIC_TRUTH } from "../../lib/public-truth";');
    expect(webAbout).toContain('const leaderboardCategoryCount = ORDERED_SLUGS.length;');
    expect(webAbout).toContain('PUBLIC_TRUTH.servicesLabel');
    expect(webAbout).toContain('PUBLIC_TRUTH.categoriesLabel');
    expect(webAbout).not.toContain('645+ services across 90+ categories');

    expect(webSearch).toContain('const servicesLabel = PUBLIC_TRUTH.servicesLabel;');
    expect(webSearch).toContain('Search across {servicesLabel} scored APIs and developer tools.');
    expect(webSearch).not.toContain('getServiceCount');
  });

  it("keeps leaderboard hub metadata aligned with the 11-category leaderboard surface", () => {
    expect(webLeaderboard).toContain('const leaderboardCategoryCount = ORDERED_SLUGS.length;');
    expect(webLeaderboard).toContain('${leaderboardCategoryCount} categories');
    expect(webLeaderboard).not.toContain('90+ categories');

    expect(astroLeaderboardHub).toContain('const leaderboardCategoryCount = ORDERED_SLUGS.length;');
    expect(astroLeaderboardHub).toContain('${leaderboardCategoryCount} categories');
    expect(astroLeaderboardHub).not.toContain('11 categories');
  });

  it("keeps high-visibility astro blog authority surfaces pinned to current public truth", () => {
    expect(astroHowToEvaluate).toContain('import { PUBLIC_TRUTH } from "../../lib/public-truth";');
    expect(astroHowToEvaluate).toContain('const servicesLabel = PUBLIC_TRUTH.servicesLabel;');
    expect(astroHowToEvaluate).toContain('const categoriesLabel = PUBLIC_TRUTH.categoriesLabel;');
    expect(astroHowToEvaluate).not.toContain('665+ scored services');
    expect(astroHowToEvaluate).not.toContain('600+ developer tools across 90+ categories');

    expect(astroMultiProviderMcp).toContain('import { PUBLIC_TRUTH } from "../../lib/public-truth";');
    expect(astroMultiProviderMcp).toContain('const servicesLabel = PUBLIC_TRUTH.servicesLabel;');
    expect(astroMultiProviderMcp).toContain('const categoriesLabel = PUBLIC_TRUTH.categoriesLabel;');
    expect(astroMultiProviderMcp).toContain('const leaderboardCategoryCount = ORDERED_SLUGS.length;');
    expect(astroMultiProviderMcp).not.toContain('The full leaderboard across 92 categories');
    expect(astroMultiProviderMcp).not.toContain('1,000+ APIs');

    expect(astroBlogIndex).toContain('const servicesLabel = PUBLIC_TRUTH.servicesLabel;');
    expect(astroBlogIndex).not.toContain('proxies 1,000+ APIs');
    expect(astroBlogIndex).not.toContain('665+ scored services');

    expect(astroWallets).toContain('import { PUBLIC_TRUTH } from "../../lib/public-truth";');
    expect(astroWallets).toContain('const servicesLabel = PUBLIC_TRUTH.servicesLabel;');
    expect(astroWallets).not.toContain('We score 1,000+ APIs on 20 dimensions for AI agent compatibility.');
  });

  it("keeps high-visibility web authority surfaces pinned to current public truth", () => {
    expect(webBlogHowToEvaluate).toContain('const servicesLabel = PUBLIC_TRUTH.servicesLabel;');
    expect(webBlogHowToEvaluate).toContain('const categoriesLabel = PUBLIC_TRUTH.categoriesLabel;');
    expect(webBlogHowToEvaluate).not.toContain('665+ scored services');
    expect(webBlogHowToEvaluate).not.toContain('600+ developer tools across 90+ categories');
    expect(webBlogHowToEvaluate).not.toContain('Compare 600+ APIs across execution and access readiness.');

    expect(webBlogAag).toContain('const servicesLabel = PUBLIC_TRUTH.servicesLabel;');
    expect(webBlogAag).toContain('const categoriesLabel = PUBLIC_TRUTH.categoriesLabel;');
    expect(webBlogAag).not.toContain('600+ developer tools across 90+ categories');

    expect(webBlogPayments).toContain('const servicesLabel = PUBLIC_TRUTH.servicesLabel;');
    expect(webBlogPayments).toContain('const categoriesLabel = PUBLIC_TRUTH.categoriesLabel;');
    expect(webBlogPayments).not.toContain('600+ developer tools across 90+ categories');

    expect(webBlogSelfScore).toContain('const servicesLabel = PUBLIC_TRUTH.servicesLabel;');
    expect(webBlogSelfScore).toContain('const categoriesLabel = PUBLIC_TRUTH.categoriesLabel;');
    expect(webBlogSelfScore).not.toContain('600+ developer tools across 90+ categories');
  });

  it("keeps the astro about and search authority surfaces pinned to canonical public truth", () => {
    expect(astroAbout).toContain('PUBLIC_TRUTH.servicesLabel');
    expect(astroAbout).toContain('PUBLIC_TRUTH.categoriesLabel');
    expect(astroAbout).not.toContain('const services = await getServices()');

    expect(astroSearch).toContain('const servicesLabel = PUBLIC_TRUTH.servicesLabel;');
    expect(astroSearch).toContain('Search across {servicesLabel} scored services.');
    expect(astroSearch).not.toContain('getServiceCount');
  });

  it("keeps the astro security auth surface aligned with the live execution rails", () => {
    expect(astroSecurity).toContain('wallet-prefund repeat traffic authenticate with X-Rhumb-Key');
    expect(astroSecurity).toContain('x402 per-call uses X-Payment from the payer wallet');
    expect(astroSecurity).toContain('BYOK routes through provider-scoped credentials via Rhumb');
    expect(astroSecurity).not.toContain('API key authentication (X-Rhumb-Key header) for managed billing. x402 payment-as-auth for autonomous agents.');
  });

  it("keeps the astro homepage x402 callout aligned with the live execution rails", () => {
    expect(astroHome).toContain('zero-signup, request-level payment authorization is the point');
    expect(astroHome).toContain('governed API key or wallet-prefund on X-Rhumb-Key');
    expect(astroHome).toContain('use BYOK when provider control is the point');
    expect(astroHome).not.toContain('For repeat traffic, the default path is still API key or wallet-prefund.');
  });

  it("keeps the capabilities MCP CTA aligned with the live execution rails", () => {
    expect(astroCapabilities).toContain('Most MCP execution starts with <code class="text-amber">RHUMB_API_KEY</code>');
    expect(astroCapabilities).toContain('governed or wallet-prefund path');
    expect(astroCapabilities).toContain('BYOK credentials where supported');
    expect(astroCapabilities).toContain('<code class="text-amber">x_payment</code>');
    expect(astroCapabilities).toContain('capabilities that expose x402 per-call');
    expect(astroCapabilities).not.toContain('Discovery works without a key; governed execution uses <code class="text-amber">RHUMB_API_KEY</code> or wallet-prefund.');
  });

  it("keeps llms discovery surfaces aligned with live rail-based pricing truth", () => {
    expect(astroLlmsRoute).toContain("Execution: governed API key, wallet-prefund, x402 per-call, or BYOK");
    expect(astroLlmsRoute).toContain("No subscriptions, no seat fees, no minimums");
    expect(astroLlmsRoute).toContain("Live pricing and markup terms: https://rhumb.dev/pricing");
    expect(astroLlmsRoute).not.toContain("upstream cost +");

    expect(rootLlms).toContain("## Execution (requires a live rail)");
    expect(rootLlms).toContain("Wallet-prefund: add balance first");
    expect(rootLlms).toContain("wallet-prefund");
    expect(rootLlms).toContain("No subscriptions, no seat fees, no minimums");
    expect(rootLlms).toContain("Live pricing and markup terms: https://rhumb.dev/pricing");
    expect(rootLlms).not.toContain("Free tier: 1,000 calls/month");
    expect(rootLlms).not.toContain("## Execution (requires API key or x402 payment)");

    expect(webPublicLlms).toContain("## Execution (requires a live rail)");
    expect(webPublicLlms).toContain("Wallet-prefund: add balance first");
    expect(webPublicLlms).toContain("wallet-prefund");
    expect(webPublicLlms).toContain("No subscriptions, no seat fees, no minimums");
    expect(webPublicLlms).toContain("Live pricing and markup terms: https://rhumb.dev/pricing");
    expect(webPublicLlms).not.toContain("Free tier: 1,000 calls/month");
    expect(webPublicLlms).not.toContain("## Execution (requires API key or x402 payment)");

    expect(webPublicLlms).toBe(rootLlms);
  });

  it("keeps agent-capabilities pricing truth aligned with live rail-based pricing story", () => {
    const rootCaps = JSON.parse(rootAgentCapabilities);
    const wellKnownCaps = JSON.parse(wellKnownAgentCapabilities);

    for (const caps of [rootCaps, wellKnownCaps]) {
      expect(caps).toHaveProperty("pricing");
      expect(caps.pricing.discovery).toBe("free");
      expect(caps.pricing.execution).toBe("rail_based");
      expect(caps.pricing.free_tier).toBeNull();
      expect(caps.pricing.details).toBe("https://rhumb.dev/pricing");
    }

    expect(rootCaps).toEqual(wellKnownCaps);
    expect(rootAgentCapabilities).not.toContain("1000_calls_per_month");
    expect(wellKnownAgentCapabilities).not.toContain("1000_calls_per_month");
  });

  it("keeps the API pricing example aligned with canonical pricing truth", () => {
    const pricingExample = extractPricingExampleJson(apiDocs);

    expect(pricingExample.error).toBeNull();
    expect(pricingExample.data.pricing_version).toBe(canonicalPricing.pricing_version);
    expect(pricingExample.data.published_at).toBe(canonicalPricing.published_at);
    expect(pricingExample.data.public_pricing_url).toBe(canonicalPricing.public_pricing_url);
    expect(pricingExample.data.canonical_api_base_url).toBe(canonicalPricing.canonical_api_base_url);
    expect(pricingExample.data.free_tier).toBe(canonicalPricing.free_tier);
    expect(pricingExample.data.modes.rhumb_managed.margin_percent).toBe(
      canonicalPricing.modes.rhumb_managed.margin_percent,
    );
    expect(pricingExample.data.modes.x402.margin_percent).toBe(
      canonicalPricing.modes.x402.margin_percent,
    );
    expect(pricingExample.data.modes.x402.network).toBe(canonicalPricing.modes.x402.network);
    expect(pricingExample.data.modes.x402.token).toBe(canonicalPricing.modes.x402.token);
    expect(pricingExample.data.modes.byok.upstream_passthrough).toBe(
      canonicalPricing.modes.byok.upstream_passthrough,
    );
    expect(pricingExample.data.modes.byok.margin_percent).toBe(
      canonicalPricing.modes.byok.margin_percent,
    );

    expect(apiDocs).not.toContain("included_executions_per_month");
  });
});

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
const astroPublicTruth = readFileSync(new URL("../../astro-web/src/lib/public-truth.ts", import.meta.url), "utf8");
const astroGettingStartedMcp = readFileSync(new URL("../../astro-web/src/pages/blog/getting-started-mcp.astro", import.meta.url), "utf8");
const astroHome = readFileSync(new URL("../../astro-web/src/pages/index.astro", import.meta.url), "utf8");
const astroLeaderboardHub = readFileSync(new URL("../../astro-web/src/pages/leaderboard/index.astro", import.meta.url), "utf8");
const astroPaymentsAgent = readFileSync(new URL("../../astro-web/src/pages/payments/agent.astro", import.meta.url), "utf8");
const astroSecuringKeys = readFileSync(new URL("../../astro-web/src/pages/blog/securing-keys-for-agents.astro", import.meta.url), "utf8");
const astroSwitchingFromSmithery = readFileSync(new URL("../../astro-web/src/pages/blog/switching-from-smithery.astro", import.meta.url), "utf8");
const astroHowToEvaluate = readFileSync(new URL("../../astro-web/src/pages/blog/how-to-evaluate-apis-for-agents.astro", import.meta.url), "utf8");
const astroBlogAag = readFileSync(new URL("../../astro-web/src/pages/blog/aag-framework.astro", import.meta.url), "utf8");
const astroBlogPayments = readFileSync(new URL("../../astro-web/src/pages/blog/payments-for-agents.astro", import.meta.url), "utf8");
const astroBlogSelfScore = readFileSync(new URL("../../astro-web/src/pages/blog/self-score.astro", import.meta.url), "utf8");
const astroMultiProviderMcp = readFileSync(new URL("../../astro-web/src/pages/blog/what-nobody-tells-you-building-multi-provider-mcp-server.astro", import.meta.url), "utf8");
const astroWallets = readFileSync(new URL("../../astro-web/src/pages/blog/why-agent-wallets-keep-losing-money.astro", import.meta.url), "utf8");
const astroX402Dogfood = readFileSync(new URL("../../astro-web/src/pages/blog/how-agents-actually-pay-x402-dogfood.astro", import.meta.url), "utf8");
const astroLlmsRoute = readFileSync(new URL("../../astro-web/src/pages/llms.txt.ts", import.meta.url), "utf8");
const astroSearch = readFileSync(new URL("../../astro-web/src/pages/search.astro", import.meta.url), "utf8");
const astroQuickstart = readFileSync(new URL("../../astro-web/src/pages/quickstart.astro", import.meta.url), "utf8");
const astroSecurity = readFileSync(new URL("../../astro-web/src/pages/security.astro", import.meta.url), "utf8");
const astroCapabilities = readFileSync(new URL("../../astro-web/src/pages/capabilities.astro", import.meta.url), "utf8");
const rootReadme = readFileSync(new URL("../../../README.md", import.meta.url), "utf8");
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
    expect(webAbout).toContain('Before you rely on Rhumb’s claims');
    expect(webAbout).toContain('href="/trust"');
    expect(webAbout).toContain('href="/methodology"');
    expect(webAbout).toContain('href="/providers#dispute-a-score"');
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

    expect(astroBlogAag).toContain('import { PUBLIC_TRUTH } from "../../lib/public-truth";');
    expect(astroBlogAag).toContain('const servicesLabel = PUBLIC_TRUTH.servicesLabel;');
    expect(astroBlogAag).toContain('const categoriesLabel = PUBLIC_TRUTH.categoriesLabel;');
    expect(astroBlogAag).not.toContain('We\'ve scored 55 developer tools across 10 categories');

    expect(astroBlogPayments).toContain('import { PUBLIC_TRUTH } from "../../lib/public-truth";');
    expect(astroBlogPayments).toContain('const servicesLabel = PUBLIC_TRUTH.servicesLabel;');
    expect(astroBlogPayments).toContain('const categoriesLabel = PUBLIC_TRUTH.categoriesLabel;');
    expect(astroBlogPayments).not.toContain('We\'ve scored 50+ developer tools across 10 categories.');

    expect(astroBlogSelfScore).toContain('import { PUBLIC_TRUTH } from "../../lib/public-truth";');
    expect(astroBlogSelfScore).toContain('const servicesLabel = PUBLIC_TRUTH.servicesLabel;');
    expect(astroBlogSelfScore).toContain('const categoriesLabel = PUBLIC_TRUTH.categoriesLabel;');
    expect(astroBlogSelfScore).not.toContain('We\'ve scored 53 developer tools across 10 categories.');

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

    expect(astroX402Dogfood).toContain('import { PUBLIC_TRUTH } from "../../lib/public-truth";');
    expect(astroX402Dogfood).toContain('const servicesLabel = PUBLIC_TRUTH.servicesLabel;');
    expect(astroX402Dogfood).toContain('Search {servicesLabel} scored services');
    expect(astroX402Dogfood).not.toContain('Search 1,000+ scored services');
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

  it("keeps the shared astro public truth default path aligned with the live execution rails", () => {
    expect(astroPublicTruth).toContain('then execute through Layer 2 with governed API key or wallet-prefund on `X-Rhumb-Key`.');
    expect(astroPublicTruth).toContain('Bring BYOK or Agent Vault only when the workflow touches your own systems.');
    expect(astroPublicTruth).not.toContain('wallet-prefunded API key');
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

  it("keeps the astro quickstart default auth rail aligned with the live execution rails", () => {
    expect(astroQuickstart).toContain('Use governed API key or wallet-prefund on <code class="text-amber">X-Rhumb-Key</code> for repeat calls.');
    expect(astroQuickstart).toContain('Bring BYOK only when provider control is the point.');
    expect(astroQuickstart).toContain('Use x402 only when zero-signup per-call payment is the point.');
    expect(astroQuickstart).not.toContain('Use a governed API key or wallet-prefunded API key for repeat calls. Use x402 only when zero-signup per-call payment is the point.');
  });

  it("keeps the astro MCP getting-started auth rail aligned with the live execution rails", () => {
    expect(astroGettingStartedMcp).toContain('For repeat traffic, use governed API key or wallet-prefund on <strong class="text-slate-100">X-Rhumb-Key</strong>.');
    expect(astroGettingStartedMcp).toContain('Bring BYOK only when provider control is the point.');
    expect(astroGettingStartedMcp).toContain('Zero-signup per-call payment matters more than repeat throughput.');
    expect(astroGettingStartedMcp).not.toContain('For repeat traffic, use <strong class="text-slate-100">RHUMB_API_KEY</strong> via governed account or wallet-prefund.');
  });

  it("keeps the astro agent-payments default production path aligned with the live execution rails", () => {
    expect(astroPaymentsAgent).toContain('Most repeat traffic should run through <strong class="text-slate-100">Layer 2</strong> with governed API key or wallet-prefund on <strong class="text-slate-100">X-Rhumb-Key</strong>.');
    expect(astroPaymentsAgent).toContain('Bring BYOK only when provider control is the point.');
    expect(astroPaymentsAgent).toContain('Zero-signup, request-level payment authorization matters more than repeat throughput');
    expect(astroPaymentsAgent).not.toContain('Most repeat traffic should run through <strong class="text-slate-100">Layer 2</strong> with a governed API key or wallet-prefunded API key.');
  });

  it("keeps the astro Smithery migration auth rail aligned with the live execution rails", () => {
    expect(astroSwitchingFromSmithery).toContain('use governed API key or wallet-prefund on <code class="text-amber">X-Rhumb-Key</code>, and bring BYOK only when provider control is the point.');
    expect(astroSwitchingFromSmithery).toContain('zero-signup, request-level payment authorization is the point');
    expect(astroSwitchingFromSmithery).not.toContain('for that, use API key or wallet-prefund.');
  });

  it("keeps the astro key-security guide aligned with the live credential-mode and payment-rail model", () => {
    expect(astroSecuringKeys).toContain('### Mode 3: Agent Vault');
    expect(astroSecuringKeys).toContain('## x402 is a payment path, not a credential mode');
    expect(astroSecuringKeys).toContain('bring BYOK or Agent Vault only when provider control is the point.');
    expect(astroSecuringKeys).toContain('three credential modes (BYOK, managed, Agent Vault), plus where x402 fits as a payment rail.');
    expect(astroSecuringKeys).not.toContain('### Mode 3: x402 per-call payment');
    expect(astroSecuringKeys).not.toContain('three credential modes (BYOK, managed, x402)');
    expect(astroSecuringKeys).not.toContain('For repeat traffic, prefer wallet-prefund or a governed API key.');
  });

  it("keeps the capabilities MCP CTA aligned with the live execution rails", () => {
    expect(astroCapabilities).toContain('Most MCP execution starts with <code class="text-amber">RHUMB_API_KEY</code>');
    expect(astroCapabilities).toContain('governed or wallet-prefund path');
    expect(astroCapabilities).toContain('BYOK credentials where supported');
    expect(astroCapabilities).toContain('<code class="text-amber">x_payment</code>');
    expect(astroCapabilities).toContain('capabilities that expose x402 per-call');
    expect(astroCapabilities).not.toContain('Discovery works without a key; governed execution uses <code class="text-amber">RHUMB_API_KEY</code> or wallet-prefund.');
  });

  it("keeps the shared resolve mental-model auth surfaces aligned with the live execution rails", () => {
    expect(rootReadme).toContain('Default auth for repeat traffic** = governed API key or wallet-prefund on `X-Rhumb-Key`');
    expect(rootReadme).toContain('**Bring BYOK** only when provider control is the point');
    expect(rootReadme).not.toContain('wallet-prefunded API key');

    expect(astroPublicTruth).toContain('execute through Layer 2 with governed API key or wallet-prefund on `X-Rhumb-Key`.');
    expect(astroPublicTruth).toContain('Bring BYOK or Agent Vault only when the workflow touches your own systems.');
    expect(astroPublicTruth).not.toContain('governed API key or wallet-prefunded API key');
  });

  it("keeps llms discovery surfaces aligned with live rail-based pricing truth", () => {
    expect(astroLlmsRoute).toContain("Execution: governed API key, wallet-prefund, x402 per-call, or BYOK");
    expect(astroLlmsRoute).toContain("three credential modes (BYOK, managed, Agent Vault)");
    expect(astroLlmsRoute).toContain("where x402 fits as a payment rail");
    expect(astroLlmsRoute).toContain("No subscriptions, no seat fees, no minimums");
    expect(astroLlmsRoute).toContain("Live pricing and markup terms: https://rhumb.dev/pricing");
    expect(astroLlmsRoute).not.toContain("three credential modes (BYOK, managed, x402)");
    expect(astroLlmsRoute).not.toContain("upstream cost +");

    expect(rootLlms).toContain("## Execution (requires a live rail)");
    expect(rootLlms).toContain("## Execution rails");
    expect(rootLlms).toContain("## Operator-controlled credential modes");
    expect(rootLlms).toContain("Wallet-prefund: add balance first");
    expect(rootLlms).toContain("Agent Vault");
    expect(rootLlms).toContain("wallet-prefund");
    expect(rootLlms).toContain("No subscriptions, no seat fees, no minimums");
    expect(rootLlms).toContain("Live pricing and markup terms: https://rhumb.dev/pricing");
    expect(rootLlms).not.toContain("## Auth paths");
    expect(rootLlms).not.toContain("Free tier: 1,000 calls/month");
    expect(rootLlms).not.toContain("## Execution (requires API key or x402 payment)");

    expect(webPublicLlms).toContain("## Execution (requires a live rail)");
    expect(webPublicLlms).toContain("## Execution rails");
    expect(webPublicLlms).toContain("## Operator-controlled credential modes");
    expect(webPublicLlms).toContain("Wallet-prefund: add balance first");
    expect(webPublicLlms).toContain("Agent Vault");
    expect(webPublicLlms).toContain("wallet-prefund");
    expect(webPublicLlms).toContain("No subscriptions, no seat fees, no minimums");
    expect(webPublicLlms).toContain("Live pricing and markup terms: https://rhumb.dev/pricing");
    expect(webPublicLlms).not.toContain("## Auth paths");
    expect(webPublicLlms).not.toContain("Free tier: 1,000 calls/month");
    expect(webPublicLlms).not.toContain("## Execution (requires API key or x402 payment)");

    expect(webPublicLlms).toBe(rootLlms);
  });

  it("keeps the astro blog index aligned with the live credential-mode story", () => {
    expect(astroBlogIndex).toContain("Three credential modes (BYOK, managed, Agent Vault)");
    expect(astroBlogIndex).not.toContain("Three credential modes (BYOK, managed, x402)");
  });

  it("keeps agent-capabilities pricing and auth truth aligned with the live rail-based story", () => {
    const rootCaps = JSON.parse(rootAgentCapabilities);
    const wellKnownCaps = JSON.parse(wellKnownAgentCapabilities);

    for (const caps of [rootCaps, wellKnownCaps]) {
      const checkCredentialsTool = caps.capabilities.execution.tools.find(
        (tool: { name: string; description: string }) => tool.name === "check_credentials",
      );

      expect(caps).toHaveProperty("pricing");
      expect(caps.pricing.discovery).toBe("free");
      expect(caps.pricing.execution).toBe("rail_based");
      expect(caps.pricing.free_tier).toBeNull();
      expect(caps.pricing.details).toBe("https://rhumb.dev/pricing");

      expect(caps.auth.discovery).toBe("none");
      expect(caps.auth.execution).toBe("rail_based");
      expect(caps.auth.repeat_traffic).toBe("governed_api_key_or_wallet_prefund_on_x_rhumb_key");
      expect(caps.auth.zero_signup).toBe("x402_usdc");
      expect(caps.auth.provider_control).toBe("byok_or_agent_vault");
      expect(caps.capabilities.execution.description).toContain("governed API key, wallet-prefund, x402 per-call, or BYOK where supported");
      expect(checkCredentialsTool?.description).toBe(
        "Inspect live credential-mode readiness, globally or for a specific Capability",
      );
    }

    expect(rootCaps).toEqual(wellKnownCaps);
    expect(rootAgentCapabilities).not.toContain("1000_calls_per_month");
    expect(wellKnownAgentCapabilities).not.toContain("1000_calls_per_month");
    expect(rootAgentCapabilities).not.toContain("api_key_or_x402");
    expect(wellKnownAgentCapabilities).not.toContain("api_key_or_x402");
    expect(rootAgentCapabilities).not.toContain("Check what credential modes are available to you");
    expect(wellKnownAgentCapabilities).not.toContain("Check what credential modes are available to you");
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

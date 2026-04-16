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
const astroCapabilityFirstOnboarding = readFileSync(new URL("../../astro-web/src/pages/blog/capability-first-agent-onboarding.astro", import.meta.url), "utf8");
const astroDashboard = readFileSync(new URL("../../astro-web/src/pages/dashboard.astro", import.meta.url), "utf8");
const astroDocs = readFileSync(new URL("../../astro-web/src/pages/docs.astro", import.meta.url), "utf8");
const astroPrivacy = readFileSync(new URL("../../astro-web/src/pages/privacy.astro", import.meta.url), "utf8");
const astroPublicTruth = readFileSync(new URL("../../astro-web/src/lib/public-truth.ts", import.meta.url), "utf8");
const astroGettingStartedMcp = readFileSync(new URL("../../astro-web/src/pages/blog/getting-started-mcp.astro", import.meta.url), "utf8");
const astroHome = readFileSync(new URL("../../astro-web/src/pages/index.astro", import.meta.url), "utf8");
const astroResolve = readFileSync(new URL("../../astro-web/src/pages/resolve.astro", import.meta.url), "utf8");
const astroLeaderboardHub = readFileSync(new URL("../../astro-web/src/pages/leaderboard/index.astro", import.meta.url), "utf8");
const astroPaymentsAgent = readFileSync(new URL("../../astro-web/src/pages/payments/agent.astro", import.meta.url), "utf8");
const astroSecuringKeys = readFileSync(new URL("../../astro-web/src/pages/blog/securing-keys-for-agents.astro", import.meta.url), "utf8");
const astroSwitchingFromSmithery = readFileSync(new URL("../../astro-web/src/pages/blog/switching-from-smithery.astro", import.meta.url), "utf8");
const astroHowToEvaluate = readFileSync(new URL("../../astro-web/src/pages/blog/how-to-evaluate-apis-for-agents.astro", import.meta.url), "utf8");
const astroBlogAag = readFileSync(new URL("../../astro-web/src/pages/blog/aag-framework.astro", import.meta.url), "utf8");
const astroAwsStorageCompare = readFileSync(new URL("../../astro-web/src/pages/blog/aws-s3-vs-cloudflare-r2-vs-backblaze-b2.astro", import.meta.url), "utf8");
const astroBlogPayments = readFileSync(new URL("../../astro-web/src/pages/blog/payments-for-agents.astro", import.meta.url), "utf8");
const astroBlogSelfScore = readFileSync(new URL("../../astro-web/src/pages/blog/self-score.astro", import.meta.url), "utf8");
const astroBlogHowAgentsPay = readFileSync(new URL("../../astro-web/src/pages/blog/how-agents-pay.astro", import.meta.url), "utf8");
const astroBlogHowAgentsPayGuide = readFileSync(new URL("../../astro-web/public/guides/blog-how-agents-pay.md", import.meta.url), "utf8");
const astroMultiProviderMcp = readFileSync(new URL("../../astro-web/src/pages/blog/what-nobody-tells-you-building-multi-provider-mcp-server.astro", import.meta.url), "utf8");
const astroWallets = readFileSync(new URL("../../astro-web/src/pages/blog/why-agent-wallets-keep-losing-money.astro", import.meta.url), "utf8");
const astroX402Dogfood = readFileSync(new URL("../../astro-web/src/pages/blog/how-agents-actually-pay-x402-dogfood.astro", import.meta.url), "utf8");
const astroLlmsRoute = readFileSync(new URL("../../astro-web/src/pages/llms.txt.ts", import.meta.url), "utf8");
const astroSearch = readFileSync(new URL("../../astro-web/src/pages/search.astro", import.meta.url), "utf8");
const astroStartManagedExecution = readFileSync(new URL("../../astro-web/src/pages/start-managed-execution.astro", import.meta.url), "utf8");
const astroQuickstart = readFileSync(new URL("../../astro-web/src/pages/quickstart.astro", import.meta.url), "utf8");
const astroSecurity = readFileSync(new URL("../../astro-web/src/pages/security.astro", import.meta.url), "utf8");
const astroCapabilities = readFileSync(new URL("../../astro-web/src/pages/capabilities.astro", import.meta.url), "utf8");
const astroLogin = readFileSync(new URL("../../astro-web/src/pages/auth/login.astro", import.meta.url), "utf8");
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
    expect(layout).toContain("BYOK or Agent Vault");
    expect(layout).toContain("BYOK and Agent Vault provider-control modes");
    expect(layout).toContain("Discovery, scoring, and browsing are free");
    expect(layout).toContain("governed API key, wallet-prefund, or x402 per-call rails");

    expect(layout).not.toContain("Free tier: 1,000 executions/month");
    expect(layout).not.toContain('"ai:free-tier": "1000 executions/month"');
    expect(layout).not.toContain('name: "Free Tier"');
    expect(layout).not.toContain("npx rhumb-mcp@0.6.0");
    expect(layout).not.toContain("x402 per-call, or BYOK");
    expect(layout).not.toContain("BYOK execution rails");
  });

  it("removes stale free-tier and split-markup claims from legal and glossary surfaces", () => {
    expect(terms).toContain("governed API key or wallet-prefund on <code class=\"text-amber\">X-Rhumb-Key</code>");
    expect(terms).toContain("BYOK or Agent Vault where supported");
    expect(terms).toContain("BYOK or Agent Vault provider-controlled routes do not add markup to the credential itself");
    expect(terms).toContain("current pricing and markup terms are published");
    expect(terms).not.toContain("A free tier provides 1,000 calls per month");
    expect(terms).not.toContain("15% for x402/USDC");
    expect(terms).not.toContain("or BYOK depending on the rail you choose");
    expect(terms).not.toContain("BYOK routes do not add markup to the credential itself");

    expect(glossary).toContain("wallet-prefund");
    expect(glossary).toContain("provider-controlled paths through BYOK or Agent Vault");
    expect(glossary).toContain("Confirm per-call pricing, x402 rail, and BYOK or Agent Vault terms.");
    expect(glossary).toContain("x402, BYOK, Agent Vault, Rhumb-managed capabilities, and more.");
    expect(glossary).toContain("Choosing a credential path? Check <a href=\"/pricing\"");
    expect(glossary).toContain("Rhumb-managed");
    expect(glossary).toContain('href: "#rhumb-managed"');
    expect(glossary).toContain('url: `https://rhumb.dev/glossary#${term.id}`');
    expect(glossary).toContain('id: "rhumb-managed"');
    expect(glossary).toContain("Discovery is free, and execution pricing lives on /pricing.");
    expect(glossary).not.toContain("public free tier includes 1,000 calls per month");
    expect(glossary).not.toContain("Confirm per-call pricing, x402 rail, and BYOK terms.");
    expect(glossary).not.toContain("x402 per-call, or BYOK");
    expect(glossary).not.toContain("call modes");
    expect(glossary).not.toContain("credential mode");
    expect(glossary).not.toContain("managed mode");
    expect(glossary).not.toContain('#managed-mode');
    expect(glossary).not.toContain('id: "managed-mode"');
    expect(glossary).not.toContain('https://rhumb.dev/glossary#managed-mode');
  });

  it("keeps the astro docs authority surface pinned to canonical public truth", () => {
    expect(astroDocs).toContain('const servicesLabel = PUBLIC_TRUTH.servicesLabel;');
    expect(astroDocs).toContain('Search ${servicesLabel} scored services');
    expect(astroDocs).toContain('>Credential paths</p>');
    expect(astroDocs).not.toContain('>Credential modes</p>');
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
    expect(astroX402Dogfood).toContain('or use a governed API key / Stripe checkout.');
    expect(astroX402Dogfood).not.toContain('Search 1,000+ scored services');
    expect(astroX402Dogfood).not.toContain('or use a Rhumb API key / Stripe checkout.');

    expect(astroBlogHowAgentsPay).toContain("wallet-prefund");
    expect(astroBlogHowAgentsPay).toContain("BYOK or Agent Vault");
    expect(astroBlogHowAgentsPayGuide).toContain("On Rhumb, you choose an execution rail first");
    expect(astroBlogHowAgentsPayGuide).toContain("how Rhumb maps governed API key, wallet-prefund, and x402 rails");
    expect(astroBlogHowAgentsPayGuide).not.toContain("hands the agent an API key");
    expect(astroBlogHowAgentsPayGuide).not.toContain("how Rhumb implements all three payment paths");
    expect(astroBlogHowAgentsPayGuide).not.toContain("X-Api-Key: rhumb_live_");
    expect(astroBlogHowAgentsPayGuide).not.toContain("rhumb_live_");
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
    expect(astroAbout).toContain('accepts payment\n            via governed API key, wallet-prefund, or on-chain USDC.');
    expect(astroAbout).not.toContain('const services = await getServices()');
    expect(astroAbout).not.toContain('accepts payment\n            via API keys or on-chain USDC.');

    expect(astroSearch).toContain('const servicesLabel = PUBLIC_TRUTH.servicesLabel;');
    expect(astroSearch).toContain('Search across {servicesLabel} scored services.');
    expect(astroSearch).not.toContain('getServiceCount');
  });

  it("keeps the shared astro public truth default path aligned with the live execution rails", () => {
    expect(astroPublicTruth).toContain('Default path: start with governed API key or wallet-prefund on `X-Rhumb-Key`, discover a Service, choose a Capability, estimate the call, then execute through Layer 2.');
    expect(astroPublicTruth).toContain('Bring BYOK or Agent Vault only when the workflow touches your own systems.');
    expect(astroPublicTruth).not.toContain('wallet-prefunded API key');
    expect(astroPublicTruth).not.toContain('give your agent one key');
  });

  it("keeps the astro security auth surface aligned with the live execution rails", () => {
    expect(astroSecurity).toContain('BYOK and Agent Vault credentials are scoped per-agent and never shared across accounts');
    expect(astroSecurity).toContain('wallet-prefund repeat traffic authenticate with X-Rhumb-Key');
    expect(astroSecurity).toContain('x402 per-call uses X-Payment from the payer wallet');
    expect(astroSecurity).toContain('BYOK and Agent Vault provider-control paths route through provider-scoped credentials via Rhumb');
    expect(astroSecurity).not.toContain('BYOK routes through provider-scoped credentials via Rhumb');
    expect(astroSecurity).not.toContain('API key authentication (X-Rhumb-Key header) for managed billing. x402 payment-as-auth for autonomous agents.');
  });

  it("keeps the astro homepage x402 callout aligned with the live execution rails", () => {
    expect(astroHome).toContain('<h3 class="font-display font-semibold text-slate-100 text-lg">Governed API key</h3>');
    expect(astroHome).toContain('Use governed API key when you want account-funded routing, failover, and billing on the default repeat-traffic rail.');
    expect(astroHome).toContain('Use BYOK or Agent Vault with your existing stack');
    expect(astroHome).toContain('Bring BYOK or Agent Vault when provider control is the point.');
    expect(astroHome).toContain('BYOK / Agent Vault');
    expect(astroHome).toContain('Use BYOK for direct pass-through, or Agent Vault when you need encrypted provider credential injection at call time, enterprise boundaries, or existing vendor accounts.');
    expect(astroHome).toContain('Start with the path that matches your job.');
    expect(astroHome).toContain('Guide &middot; Credential paths and storage');
    expect(astroHome).toContain('See secure credential paths &rarr;');
    expect(astroHome).toContain('zero-signup, request-level payment authorization is the point');
    expect(astroHome).toContain('governed API key or wallet-prefund on X-Rhumb-Key');
    expect(astroHome).toContain('use BYOK or Agent Vault when provider control is the point');
    expect(astroHome).not.toContain('Start with the mode that matches your job.');
    expect(astroHome).not.toContain('Guide &middot; Three credential modes');
    expect(astroHome).not.toContain('See credential modes &rarr;');
    expect(astroHome).not.toContain('Bring your own provider credentials directly');
    expect(astroHome).not.toContain('<h3 class="font-display font-semibold text-slate-100 text-lg">API key</h3>');
    expect(astroHome).not.toContain('Use BYOK, Agent Vault, or your existing stack');
    expect(astroHome).not.toContain('use BYOK when provider control is the point');
    expect(astroHome).not.toContain('For repeat traffic, the default path is still API key or wallet-prefund.');
    expect(astroHome).not.toContain('Use Rhumb-managed execution when you want routing, failover, and billing under one key.');
    expect(astroHome).not.toContain('Use governed API key when you want routing, failover, and billing under one key.');
  });

  it("keeps the astro quickstart default auth rail aligned with the live execution rails", () => {
    expect(astroQuickstart).toContain('Use governed API key or wallet-prefund on <code class="text-amber">X-Rhumb-Key</code> for repeat calls.');
    expect(astroQuickstart).toContain('Bring BYOK or Agent Vault only when provider control is the point.');
    expect(astroQuickstart).toContain('Execute through governed API key first');
    expect(astroQuickstart).toContain('BYOK / Agent Vault');
    expect(astroQuickstart).toContain('Use BYOK for direct pass-through, or Agent Vault for encrypted provider credential injection when provider control is the point.');
    expect(astroQuickstart).toContain('BYOK, Agent Vault, governed API key, wallet-prefund, x402 — which path fits your agent');
    expect(astroQuickstart).toContain('Execute via governed API key');
    expect(astroQuickstart).toContain('Governed API key</h3>');
    expect(astroQuickstart).toContain('Execute via wallet-prefund');
    expect(astroQuickstart).toContain('wallet-scoped X-Rhumb-Key credential');
    expect(astroQuickstart).toContain('Request execution without a governed API key');
    expect(astroQuickstart).toContain('use the standard governed API key rail.');
    expect(astroQuickstart).not.toContain('Bring BYOK only when provider control is the point.');
    expect(astroQuickstart).not.toContain('Pass your service API key directly. BYOK = full control.');
    expect(astroQuickstart).toContain('Use x402 only when zero-signup per-call payment is the point.');
    expect(astroQuickstart).toContain('The change is the credential path, not the product mental model.');
    expect(astroQuickstart).not.toContain('The change is the credential mode, not the product mental model.');
    expect(astroQuickstart).not.toContain('Use a governed API key or wallet-prefunded API key for repeat calls. Use x402 only when zero-signup per-call payment is the point.');
    expect(astroQuickstart).not.toContain('BYOK, Agent Vault, API key, wallet-prefund, x402 — which path fits your agent');
    expect(astroQuickstart).not.toContain('Execute through one key first');
    expect(astroQuickstart).not.toContain('Layer 2 with one key');
    expect(astroQuickstart).not.toContain('API Key</h3>');
    expect(astroQuickstart).not.toContain('Execute via API key');
    expect(astroQuickstart).not.toContain('Execute via wallet-prefunded balance');
    expect(astroQuickstart).not.toContain('wallet-scoped API key');
    expect(astroQuickstart).not.toContain('Request execution without an API key');
    expect(astroQuickstart).not.toContain('use the standard API-key rail.');
  });

  it("keeps the astro MCP getting-started auth rail aligned with the live execution rails", () => {
    const gettingStartedManagedCard = 'Governed path</span>\n                <span class="font-semibold text-slate-200">Rhumb-managed</span>';
    const gettingStartedByokCard = 'Provider-controlled</span>\n                <span class="font-semibold text-slate-200">BYOK</span>';
    const gettingStartedVaultCard = 'Provider-controlled</span>\n                <span class="font-semibold text-slate-200">Agent Vault</span>';

    expect(astroGettingStartedMcp).toContain('No governed API key required for discovery and scoring. Add to any MCP-compatible client.');
    expect(astroGettingStartedMcp).toContain('For repeat traffic, use governed API key or wallet-prefund on <strong class="text-slate-100">X-Rhumb-Key</strong>.');
    expect(astroGettingStartedMcp).toContain('Bring BYOK or Agent Vault only when provider control is the point.');
    expect(astroGettingStartedMcp).toContain('Rhumb supports three live credential paths. Start with the Rhumb-managed path when zero-config governed execution is the point, then bring BYOK or Agent Vault in only when provider control matters.');
    expect(astroGettingStartedMcp).toContain(gettingStartedManagedCard);
    expect(astroGettingStartedMcp).toContain(gettingStartedByokCard);
    expect(astroGettingStartedMcp).toContain(gettingStartedVaultCard);
    expect(astroGettingStartedMcp.indexOf(gettingStartedManagedCard)).toBeLessThan(astroGettingStartedMcp.indexOf(gettingStartedByokCard));
    expect(astroGettingStartedMcp.indexOf(gettingStartedByokCard)).toBeLessThan(astroGettingStartedMcp.indexOf(gettingStartedVaultCard));
    expect(astroGettingStartedMcp).not.toContain('Rhumb supports three live credential paths. Keep provider-controlled execution on BYOK or Agent Vault, and use the Rhumb-managed path when zero-config governed execution is the point.');
    expect(astroGettingStartedMcp).not.toContain('Rhumb-Managed');
    expect(astroGettingStartedMcp).not.toContain('Bring BYOK only when provider control is the point.');
    expect(astroGettingStartedMcp).not.toContain('No API key required for discovery and scoring. Add to any MCP-compatible client.');
    expect(astroGettingStartedMcp).not.toContain('No API key needed for read endpoints.');
    expect(astroGettingStartedMcp).not.toContain('Mode 1');
    expect(astroGettingStartedMcp).not.toContain('Mode 2');
    expect(astroGettingStartedMcp).not.toContain('Mode 3');
    expect(astroGettingStartedMcp).toContain('Zero-signup per-call payment matters more than repeat throughput.');
    expect(astroGettingStartedMcp).toContain('Get step-by-step instructions for obtaining provider credentials');
    expect(astroGettingStartedMcp).toContain('No governed API key needed for read endpoints.');
    expect(astroGettingStartedMcp).toContain('Pass your own provider API key at execution time. Rhumb routes the request, you keep control of the provider credential.');
    expect(astroGettingStartedMcp).not.toContain('Pass your own API keys at execution time. Rhumb routes the request, you own the credential.');
    expect(astroGettingStartedMcp).not.toContain('Setup guides for credential modes');
    expect(astroGettingStartedMcp).not.toContain('For repeat traffic, use <strong class="text-slate-100">RHUMB_API_KEY</strong> via governed account or wallet-prefund.');
  });

  it("keeps storage comparison copy aligned with the full provider-control model", () => {
    expect(astroAwsStorageCompare).toContain('IAM scoping enables secure provider-controlled patterns, whether you pass BYOK directly or inject credentials through Agent Vault.');
    expect(astroAwsStorageCompare).not.toContain('IAM scoping enables secure BYOK patterns.');
  });

  it("keeps the astro agent-payments default production path aligned with the live execution rails", () => {
    expect(astroPaymentsAgent).toContain('Most repeat traffic should run through <strong class="text-slate-100">Layer 2</strong> with governed API key or wallet-prefund on <strong class="text-slate-100">X-Rhumb-Key</strong>.');
    expect(astroPaymentsAgent).toContain('Bring BYOK or Agent Vault only when provider control is the point.');
    expect(astroPaymentsAgent).toContain('Call the execution endpoint without a governed API key when you want the payment rail to handle authorization.');
    expect(astroPaymentsAgent).toContain('provisioning a governed API key would add avoidable friction.');
    expect(astroPaymentsAgent).toContain('reusable governed API key');
    expect(astroPaymentsAgent).toContain('standard governed API key rail instead of assuming drop-in x402 interoperability.');
    expect(astroPaymentsAgent).toContain('request execution without a governed API key');
    expect(astroPaymentsAgent).toContain('Request execution without a governed API key, pay the exact 402 requirement, then retry with X-Payment from the same wallet.');
    expect(astroPaymentsAgent).toContain('wallet-scoped X-Rhumb-Key credential');
    expect(astroPaymentsAgent).not.toContain('Bring BYOK only when provider control is the point.');
    expect(astroPaymentsAgent).toContain('Zero-signup, request-level payment authorization matters more than repeat throughput');
    expect(astroPaymentsAgent).not.toContain('provisioning an API key would add avoidable friction.');
    expect(astroPaymentsAgent).not.toContain('Most repeat traffic should run through <strong class="text-slate-100">Layer 2</strong> with a governed API key or wallet-prefunded API key.');
    expect(astroPaymentsAgent).not.toContain('Call the execution endpoint without an API key when you want the payment rail to handle authorization.');
    expect(astroPaymentsAgent).not.toContain('reusable API key');
    expect(astroPaymentsAgent).not.toContain('wallet-scoped key');
    expect(astroPaymentsAgent).not.toContain('wallet-scoped API key');
    expect(astroPaymentsAgent).not.toContain('standard API-key rail instead of assuming drop-in x402 interoperability.');
    expect(astroPaymentsAgent).not.toContain('request execution without an API key');
    expect(astroPaymentsAgent).not.toContain('Request execution without a key, pay the exact 402 requirement, then retry with X-Payment from the same wallet.');
  });

  it("keeps the astro Smithery migration auth rail aligned with the live execution rails", () => {
    expect(astroSwitchingFromSmithery).toContain('import { PUBLIC_TRUTH } from "../../lib/public-truth";');
    expect(astroSwitchingFromSmithery).toContain('const servicesLabel = PUBLIC_TRUTH.servicesLabel;');
    expect(astroSwitchingFromSmithery).toContain('const categoriesLabel = PUBLIC_TRUTH.categoriesLabel;');
    expect(astroSwitchingFromSmithery).toContain('use governed API key or wallet-prefund on <code class="text-amber">X-Rhumb-Key</code>, and bring BYOK or Agent Vault only when provider control is the point.');
    expect(astroSwitchingFromSmithery).not.toContain('use governed API key or wallet-prefund on <code class="text-amber">X-Rhumb-Key</code>, and bring BYOK only when provider control is the point.');
    expect(astroSwitchingFromSmithery).toContain('dimension: "Credential paths"');
    expect(astroSwitchingFromSmithery).toContain('Three credential paths: Rhumb-managed (Rhumb holds the provider credential), BYOK (you keep the provider API key), Agent Vault');
    expect(astroSwitchingFromSmithery).toContain('Start with Rhumb-managed if you want us to handle credentials. Bring BYOK if you already have provider API keys. Use Agent Vault if you want Rhumb to inject your encrypted provider credential at call time.');
    expect(astroSwitchingFromSmithery).toContain('x402 stays separate as the zero-signup payment rail.');
    expect(astroSwitchingFromSmithery).toContain('Use x402 only when zero-signup per-call payment is the point.');
    expect(astroSwitchingFromSmithery).toContain('4,000+ server catalog (we\'re at {servicesLabel} scored services and growing daily)');
    expect(astroSwitchingFromSmithery).toContain('zero-signup, request-level payment authorization is the point');
    expect(astroSwitchingFromSmithery).not.toContain('dimension: "Credential modes"');
    expect(astroSwitchingFromSmithery).not.toContain('Three credential paths: Rhumb-managed (we hold keys), BYOK (your keys), Agent Vault');
    expect(astroSwitchingFromSmithery).not.toContain('Three credential paths: BYOK (your keys), Rhumb-managed (we hold keys), Agent Vault');
    expect(astroSwitchingFromSmithery).not.toContain('Start with Rhumb-managed if you want us to handle credentials. Bring BYOK if you already have provider keys. Use Agent Vault if you want Rhumb to inject your encrypted provider credential at call time.');
    expect(astroSwitchingFromSmithery).not.toContain('BYOK if you already have provider keys. Rhumb-managed if you want us to handle credentials. Agent Vault if you want Rhumb to inject your encrypted provider credential at call time.');
    expect(astroSwitchingFromSmithery).not.toContain('Three modes: BYOK (your keys), Rhumb-managed (we hold keys), Agent Vault');
    expect(astroSwitchingFromSmithery).not.toContain('Three modes: BYOK (your keys), Rhumb-managed (we hold keys), x402 USDC (no account needed)');
    expect(astroSwitchingFromSmithery).not.toContain('x402 if your agent should pay autonomously.');
    expect(astroSwitchingFromSmithery).not.toContain('525+ services scored across 86 categories');
    expect(astroSwitchingFromSmithery).not.toContain('for that, use API key or wallet-prefund.');
  });

  it("keeps the astro key-security guide aligned with the live credential-path and payment-rail model", () => {
    expect(astroSecuringKeys).toContain('## Three credential paths');
    expect(astroSecuringKeys).toContain('### Agent Vault');
    expect(astroSecuringKeys).toContain('## x402 is a payment path, not a credential mode');
    expect(astroSecuringKeys).toContain('bring BYOK or Agent Vault only when provider control is the point.');
    expect(astroSecuringKeys).toContain('three credential paths (Rhumb-managed, BYOK, Agent Vault), plus where x402 fits as a payment rail.');
    expect(astroSecuringKeys).toContain('Rhumb-managed, BYOK, and Agent Vault compared, plus where x402 fits as a payment rail.');
    expect(astroSecuringKeys).toContain('Three credential paths, a storage hierarchy, and honest threat modeling. No "enterprise-grade" theater.');
    expect(astroSecuringKeys).toContain('Pick the path that matches your trust model.');
    expect(astroSecuringKeys).toContain('Prefer Rhumb-managed, Agent Vault, or x402 over raw BYOK');
    expect(astroSecuringKeys).toContain('Your governed API key is the only credential to protect.');
    expect(astroSecuringKeys).toContain('Managed capabilities reduce your credential surface to a single governed API key.');
    expect(astroSecuringKeys).not.toContain('Pick the mode that matches your trust model.');
    expect(astroSecuringKeys).not.toContain('Your Rhumb API key is the only credential to protect.');
    expect(astroSecuringKeys).not.toContain('Managed capabilities reduce your credential surface to a single Rhumb API key.');
    expect(astroSecuringKeys).not.toContain('three credential paths (managed, BYOK, Agent Vault), plus where x402 fits as a payment rail.');
    expect(astroSecuringKeys).not.toContain('three credential paths (BYOK, managed, Agent Vault), plus where x402 fits as a payment rail.');
    expect(astroSecuringKeys).not.toContain('BYOK, managed, and Agent Vault compared, plus where x402 fits as a payment rail.');
    expect(astroSecuringKeys).not.toContain('Prefer managed, Agent Vault, or x402 over raw BYOK');
    expect(astroSecuringKeys).not.toContain('### Mode 1:');
    expect(astroSecuringKeys).not.toContain('### Mode 2:');
    expect(astroSecuringKeys).not.toContain('### Mode 3:');
    expect(astroSecuringKeys).not.toContain('### Mode 3: x402 per-call payment');
    expect(astroSecuringKeys).not.toContain('three credential modes (BYOK, managed, Agent Vault)');
    expect(astroSecuringKeys).not.toContain('three credential modes (BYOK, managed, x402)');
    expect(astroSecuringKeys).not.toContain('For repeat traffic, prefer wallet-prefund or a governed API key.');
  });

  it("keeps the capabilities discovery CTA aligned with resolve handoff truth", () => {
    expect(astroCapabilities).toContain('resolve ranked providers or follow the recovery handoff');
    expect(astroCapabilities).toContain('resolve ranked providers or follow the machine-readable recovery handoff');
    expect(astroCapabilities).toContain('resolve returns search suggestions instead of a blank dead end');
    expect(astroCapabilities).toContain('Most MCP execution starts with <code class="text-amber">RHUMB_API_KEY</code>');
    expect(astroCapabilities).toContain('(your governed API key)');
    expect(astroCapabilities).toContain('governed API key or wallet-prefund rails');
    expect(astroCapabilities).toContain('Bring BYOK or Agent Vault only when provider control is the point');
    expect(astroCapabilities).toContain('<code class="text-amber">x_payment</code>');
    expect(astroCapabilities).toContain('capabilities that expose x402 per-call');
    expect(astroCapabilities).not.toContain('Once you have the capability ID, resolve providers, estimate the active rail, then execute through quickstart or MCP.');
    expect(astroCapabilities).not.toContain('Discover capability definitions, resolve providers, and execute the subset that is live through');
    expect(astroCapabilities).not.toContain('Discovery works without a key; governed execution uses <code class="text-amber">RHUMB_API_KEY</code> or wallet-prefund.');
  });

  it("keeps the login execution-credit note aligned with the live access model", () => {
    expect(astroLogin).toContain('get your governed API key and access the developer dashboard.');
    expect(astroLogin).toContain('access your dashboard, governed API key, and billing controls.');
    expect(astroLogin).toContain('Run traffic through x402,');
    expect(astroLogin).toContain('use BYOK or Agent Vault where supported, or add funded balance in the dashboard.');
    expect(astroLogin).not.toContain('get your API key and access the developer dashboard.');
    expect(astroLogin).not.toContain('access your dashboard, API key, and billing controls.');
    expect(astroLogin).not.toContain('use your own provider credentials where supported');
  });

  it("keeps the dashboard funding note aligned with the live access model", () => {
    expect(astroDashboard).toContain('governed API key, usage, and quickstart.');
    expect(astroDashboard).toContain('Your dashboard access and governed API key are active');
    expect(astroDashboard).toContain('Your governed API key');
    expect(astroDashboard).toContain('Governed API key');
    expect(astroDashboard).toContain('Copy your governed API key');
    expect(astroDashboard).toContain('Rotate your governed API key? The old key will stop working immediately.');
    expect(astroDashboard).toContain('default to the governed API key path by adding funded balance below');
    expect(astroDashboard).toContain('use BYOK or Agent Vault only when provider control is the point');
    expect(astroDashboard).not.toContain('Your Rhumb developer dashboard — API key, usage, and quickstart.');
    expect(astroDashboard).not.toContain('Your dashboard access and API key are active');
    expect(astroDashboard).not.toContain('Your API Key');
    expect(astroDashboard).not.toContain('Copy your API key');
    expect(astroDashboard).not.toContain('Rotate your API key? The old key will stop working immediately.');
    expect(astroDashboard).not.toContain('use BYOK only when you need your own provider account');
  });

  it("keeps the privacy source aligned with the full provider-control model", () => {
    expect(astroPrivacy).toContain('A governed API key we generate for your account');
    expect(astroPrivacy).toContain('If you use <strong class="text-slate-200">Agent Vault</strong>, Rhumb stores an encrypted');
    expect(astroPrivacy).toContain('provider credential scoped to your agent, injects it only at call time,');
    expect(astroPrivacy).toContain('and does not share it across accounts.');
    expect(astroPrivacy).toContain('Authenticated requests are associated with your governed API key.');
    expect(astroPrivacy).not.toContain('An API key we generate for your account');
    expect(astroPrivacy).not.toContain('Authenticated requests are associated with your API key.');
    expect(astroPrivacy).not.toContain('If you use <strong class="text-slate-200">bring-your-own-key (BYOK)</strong>{" "}\n            mode, your credentials are passed through to the upstream service in the same\n            request and are <strong class="text-slate-200">not stored</strong> by Rhumb.\n          </p>');
  });

  it("keeps the astro security page aligned with governed API key auth wording", () => {
    expect(astroSecurity).toContain('Minimal data collection: email address for account creation, governed API key for authentication.');
    expect(astroSecurity).toContain('Account deletion removes all associated data: governed API keys, execution logs, billing records, and stored credentials.');
    expect(astroSecurity).not.toContain('Minimal data collection: email address for account creation, API key for authentication.');
    expect(astroSecurity).not.toContain('Account deletion removes all associated data: API keys, execution logs, billing records, and stored credentials.');
  });

  it("keeps the shared resolve mental-model auth surfaces aligned with the live execution rails", () => {
    const rootReadmeManagedRow = '| **Rhumb-managed** | Rhumb holds the credential — zero setup for the agent |';
    const rootReadmeByokRow = '| **BYOK** | Bring your own provider API key. Rhumb routes, you authenticate |';
    const rootReadmeVaultRow = '| **Agent Vault** | Your key, encrypted and stored — Rhumb injects at call time |';
    const resolveManagedCard = 'name: "Rhumb-managed"';
    const resolveByokCard = 'name: "BYOK"';
    const resolveVaultCard = 'name: "Agent Vault"';

    expect(rootReadme).toContain('### Three credential paths');
    expect(rootReadme).toContain('Zero config. Discovery tools work immediately — no signup, no governed API key.');
    expect(rootReadme).toContain('For execution, pass your governed API key:');
    expect(rootReadme).toContain('[Get a governed API key →](https://rhumb.dev/auth/login)');
    expect(rootReadme).toContain('| Path | How it works |');
    expect(rootReadme).toContain(rootReadmeManagedRow);
    expect(rootReadme).toContain(rootReadmeByokRow);
    expect(rootReadme).toContain(rootReadmeVaultRow);
    expect(rootReadme.indexOf(rootReadmeManagedRow)).toBeLessThan(rootReadme.indexOf(rootReadmeByokRow));
    expect(rootReadme.indexOf(rootReadmeByokRow)).toBeLessThan(rootReadme.indexOf(rootReadmeVaultRow));
    expect(rootReadme).toContain('**Governed API key** — sign up, get a key, prepaid credits');
    expect(rootReadme).toContain('start with governed API key or wallet-prefund on `X-Rhumb-Key`, discover a Service, choose a Capability, estimate, then execute');
    expect(rootReadme).toContain('Default auth for repeat traffic** = governed API key or wallet-prefund on `X-Rhumb-Key`');
    expect(rootReadme).toContain('**Bring BYOK or Agent Vault** only when provider control is the point');
    expect(rootReadme).not.toContain('### Three credential modes');
    expect(rootReadme).not.toContain('Zero config. Discovery tools work immediately — no signup, no API key.');
    expect(rootReadme).not.toContain('For execution, pass your Rhumb API key:');
    expect(rootReadme).not.toContain('[Get an API key →](https://rhumb.dev/auth/login)');
    expect(rootReadme).not.toContain('| Mode | How it works |');
    expect(rootReadme).not.toContain('**API key** — sign up, get a key, prepaid credits');
    expect(rootReadme).not.toContain('Bring your own API key — Rhumb routes, you authenticate');
    expect(rootReadme).not.toContain('wallet-prefunded API key');
    expect(rootReadme).not.toContain('give your agent one key');

    expect(astroPublicTruth).toContain('Default path: start with governed API key or wallet-prefund on `X-Rhumb-Key`, discover a Service, choose a Capability, estimate the call, then execute through Layer 2.');
    expect(astroPublicTruth).toContain('Bring BYOK or Agent Vault only when the workflow touches your own systems.');
    expect(astroPublicTruth).not.toContain('governed API key or wallet-prefunded API key');
    expect(astroPublicTruth).not.toContain('give your agent one key');

    expect(astroResolve).toContain('const credentialPaths = [');
    expect(astroResolve).toContain('Three credential paths, one trust story');
    expect(astroResolve).toContain('Use the managed path first');
    expect(astroResolve).toContain('{PUBLIC_TRUTH.beachheadSummary}');
    expect(astroResolve).toContain('{PUBLIC_TRUTH.callableRealitySummary}');
    expect(astroResolve).toContain('Resolve should not force every capability through the same trust model. Rhumb-managed, BYOK, and Agent Vault each exist for a reason.');
    expect(astroResolve).toContain('label: "Default magic"');
    expect(astroResolve).toContain(resolveManagedCard);
    expect(astroResolve).toContain('Best for zero-config utility capabilities where Rhumb can own the provider account and expose the capability as the product.');
    expect(astroResolve).toContain('label: "Your systems"');
    expect(astroResolve).toContain(resolveByokCard);
    expect(astroResolve).toContain('Use when the capability touches your account data, workspace, or production systems and you want direct control over the upstream credential.');
    expect(astroResolve).toContain('label: "Agent-native custody"');
    expect(astroResolve).toContain(resolveVaultCard);
    expect(astroResolve).toContain('Use when the credential should stay encrypted in Rhumb custody, scoped to the agent, and be injected only at execution time.');
    expect(astroResolve).toContain('title="Resolve | Managed superpowers first"');
    expect(astroResolve).toContain('description="Resolve gives agents managed superpowers first, then secure bridges into operator-owned systems when the workflow needs them."');
    expect(astroResolve).toContain('Managed superpowers first.');
    expect(astroResolve).toContain('title: "Managed superpowers first"');
    expect(astroResolve).toContain('starts agents on Rhumb-managed capabilities through governed API key or wallet-prefund');
    expect(astroResolve.indexOf(resolveManagedCard)).toBeLessThan(astroResolve.indexOf(resolveByokCard));
    expect(astroResolve.indexOf(resolveByokCard)).toBeLessThan(astroResolve.indexOf(resolveVaultCard));
    expect(astroResolve).toContain('href="/start-managed-execution?');
    expect(astroResolve).toContain('Start managed execution');
    expect(astroResolve).toContain('id="credential-paths"');
    expect(astroResolve).not.toContain('const modes = [');
    expect(astroResolve).not.toContain('Three modes, one trust story');
    expect(astroResolve).not.toContain('Use managed mode first');
    expect(astroResolve).not.toContain('agent-controlled storage');
    expect(astroResolve).not.toContain('One key, many superpowers');
    expect(astroResolve).not.toContain('Resolve gives agents one key for managed superpowers');

    expect(astroCapabilityFirstOnboarding).toContain('The honest production default today is still simple: start with the governed API key when you want repeat managed execution');
    expect(astroCapabilityFirstOnboarding).toContain('use x402 only when zero-signup per-call payment is the point');
    expect(astroCapabilityFirstOnboarding).toContain('bring BYOK or Agent Vault only when provider control is the point');
    expect(astroCapabilityFirstOnboarding).toContain('Capability-First Agent Onboarding: Managed Superpowers First');
    expect(astroCapabilityFirstOnboarding).toContain('The better onboarding model is managed superpowers first, then secure bridges only when needed.');
    expect(astroCapabilityFirstOnboarding).toContain('If the managed lane gives the agent a bounded capability that becomes useful immediately');
    expect(astroCapabilityFirstOnboarding).toContain('Managed superpowers first is a better product story because it is a better adoption story.');
    expect(astroCapabilityFirstOnboarding).not.toContain('bring wallet or provider-controlled paths');
    expect(astroCapabilityFirstOnboarding).toContain('href="/start-managed-execution?');
    expect(astroCapabilityFirstOnboarding).toContain('Start managed execution');
    expect(astroCapabilityFirstOnboarding).not.toContain('The honest production default today is still simple: start with the API key when you want repeat managed execution');
    expect(astroCapabilityFirstOnboarding).not.toContain('One Key, Many Superpowers');
    expect(astroCapabilityFirstOnboarding).not.toContain('one key, many superpowers');

    expect(astroStartManagedExecution).toContain('The shortest honest path into Rhumb managed execution: governed API key first, pricing before execution, and quickstart for free reads.');
    expect(astroStartManagedExecution).toContain('If you want repeat managed execution, the honest default is governed API key first.');
    expect(astroStartManagedExecution).toContain('It keeps repeat traffic on the stable X-Rhumb-Key execution header and the simplest operational model.');
    expect(astroStartManagedExecution).toContain('use x402 only when zero-signup per-call payment is the point');
    expect(astroStartManagedExecution).toContain('bring BYOK or Agent Vault only when provider control is the point');
    expect(astroStartManagedExecution).not.toContain('bring wallet or provider-controlled paths');
    expect(astroStartManagedExecution).toContain('const PATH_CHOICES = [');
    expect(astroStartManagedExecution).toContain('Get governed API key');
    expect(astroStartManagedExecution).toContain('Review pricing');
    expect(astroStartManagedExecution).toContain('Stay on free quickstart');
    expect(astroStartManagedExecution).toContain('Pick the path that matches the job');
    expect(astroStartManagedExecution).toContain('The honest default is governed API key, but the right next step still depends on whether you are evaluating, putting managed execution into repeat use, or crossing into your own systems.');
    expect(astroStartManagedExecution).toContain('eyebrow: "Default production path"');
    expect(astroStartManagedExecution).toContain('title: "Governed API key"');
    expect(astroStartManagedExecution).toContain('href: "/auth/login?rhumb_experiment=e004&rhumb_source=start-managed-execution-path-governed"');
    expect(astroStartManagedExecution).toContain('eyebrow: "Still evaluating"');
    expect(astroStartManagedExecution).toContain('title: "Quickstart first"');
    expect(astroStartManagedExecution).toContain('href: "/quickstart?rhumb_experiment=e004&rhumb_source=start-managed-execution-path-quickstart"');
    expect(astroStartManagedExecution).toContain('eyebrow: "Touches your systems"');
    expect(astroStartManagedExecution).toContain('title: "BYOK or Agent Vault"');
    expect(astroStartManagedExecution).toContain('href: "/resolve?rhumb_experiment=e004&rhumb_source=start-managed-execution-path-credentials#credential-paths"');
    expect(astroStartManagedExecution).toContain('Review credential paths');
    expect(astroStartManagedExecution.indexOf('title: "Governed API key"')).toBeLessThan(astroStartManagedExecution.indexOf('title: "Quickstart first"'));
    expect(astroStartManagedExecution.indexOf('title: "Quickstart first"')).toBeLessThan(astroStartManagedExecution.indexOf('title: "BYOK or Agent Vault"'));
    expect(astroStartManagedExecution).toContain('Governed API key is the cleanest repeat-traffic rail today.');
    expect(astroStartManagedExecution).toContain('Pricing, route checks, and cost checks should come before the first paid execution call.');
    expect(astroStartManagedExecution).toContain('Use x402 only when zero-signup per-call payment is the point, and bring BYOK or Agent Vault only when provider control is the point.');
    expect(astroStartManagedExecution).not.toContain('The shortest honest path into Rhumb managed execution: API key first, pricing before execution, and quickstart for free reads.');
    expect(astroStartManagedExecution).not.toContain('If you want repeat managed execution, the honest default is API key first.');
    expect(astroStartManagedExecution).not.toContain('It keeps one stable execution header and the simplest operational model.');
    expect(astroStartManagedExecution).not.toContain('Get API key');
  });

  it("keeps llms discovery surfaces aligned with live rail-based pricing truth", () => {
    expect(astroLlmsRoute).toContain("Execution rails: governed API key, wallet-prefund, or x402 per-call");
    expect(astroLlmsRoute).toContain("Provider-control modes where supported: BYOK and Agent Vault");
    expect(astroLlmsRoute).toContain("credential paths explained");
    expect(astroLlmsRoute).toContain("three credential paths (Rhumb-managed, BYOK, Agent Vault)");
    expect(astroLlmsRoute).toContain("Three credential paths: Rhumb-managed, BYOK, Agent Vault");
    expect(astroLlmsRoute).not.toContain("Three credential paths: BYOK, Rhumb-managed, Agent Vault");
    expect(astroLlmsRoute).not.toContain("Three credential paths: Rhumb-Managed, BYOK, Agent Vault");
    expect(astroLlmsRoute).not.toContain("Execution: governed API key, wallet-prefund, x402 per-call, or BYOK");
    expect(astroLlmsRoute).toContain("where x402 fits as a payment rail");
    expect(astroLlmsRoute).toContain("No subscriptions, no seat fees, no minimums");
    expect(astroLlmsRoute).toContain("Live pricing and markup terms: https://rhumb.dev/pricing");
    expect(astroLlmsRoute).not.toContain("credential modes explained");
    expect(astroLlmsRoute).not.toContain("three credential paths (managed, BYOK, Agent Vault)");
    expect(astroLlmsRoute).not.toContain("three credential paths (BYOK, managed, Agent Vault)");
    expect(astroLlmsRoute).not.toContain("three credential modes (BYOK, managed, Agent Vault)");
    expect(astroLlmsRoute).not.toContain("three credential modes (BYOK, managed, x402)");
    expect(astroLlmsRoute).not.toContain("upstream cost +");

    expect(rootLlms).toContain("## Execution (requires a live rail)");
    expect(rootLlms).toContain("## Execution rails");
    expect(rootLlms).toContain("## Operator-controlled credential modes");
    expect(rootLlms).toContain("3 execution rails: governed API key, wallet-prefund, x402 / USDC");
    expect(rootLlms).toContain("2 operator-controlled credential modes where supported: BYOK, Agent Vault");
    expect(rootLlms).toContain("Wallet-prefund: add balance first");
    expect(rootLlms).toContain("Execution rails: governed API key, wallet-prefund, or x402 per-call");
    expect(rootLlms).toContain("Provider-control modes where supported: BYOK and Agent Vault");
    expect(rootLlms).toContain("Agent Vault");
    expect(rootLlms).toContain("wallet-prefund");
    expect(rootLlms).toContain("No subscriptions, no seat fees, no minimums");
    expect(rootLlms).toContain("Live pricing and markup terms: https://rhumb.dev/pricing");
    expect(rootLlms).not.toContain("## Auth paths");
    expect(rootLlms).not.toContain("3 credential modes: BYOK, Rhumb-managed, Agent Vault");
    expect(rootLlms).not.toContain("Execution: governed API key, wallet-prefund, x402 per-call, or BYOK");
    expect(rootLlms).not.toContain("Free tier: 1,000 calls/month");
    expect(rootLlms).not.toContain("## Execution (requires API key or x402 payment)");

    expect(webPublicLlms).toContain("## Execution (requires a live rail)");
    expect(webPublicLlms).toContain("## Execution rails");
    expect(webPublicLlms).toContain("## Operator-controlled credential modes");
    expect(webPublicLlms).toContain("3 execution rails: governed API key, wallet-prefund, x402 / USDC");
    expect(webPublicLlms).toContain("2 operator-controlled credential modes where supported: BYOK, Agent Vault");
    expect(webPublicLlms).toContain("Wallet-prefund: add balance first");
    expect(webPublicLlms).toContain("Execution rails: governed API key, wallet-prefund, or x402 per-call");
    expect(webPublicLlms).toContain("Provider-control modes where supported: BYOK and Agent Vault");
    expect(webPublicLlms).toContain("Agent Vault");
    expect(webPublicLlms).toContain("wallet-prefund");
    expect(webPublicLlms).toContain("No subscriptions, no seat fees, no minimums");
    expect(webPublicLlms).toContain("Live pricing and markup terms: https://rhumb.dev/pricing");
    expect(webPublicLlms).not.toContain("## Auth paths");
    expect(webPublicLlms).not.toContain("3 credential modes: BYOK, Rhumb-managed, Agent Vault");
    expect(webPublicLlms).not.toContain("Execution: governed API key, wallet-prefund, x402 per-call, or BYOK");
    expect(webPublicLlms).not.toContain("Free tier: 1,000 calls/month");
    expect(webPublicLlms).not.toContain("## Execution (requires API key or x402 payment)");

    expect(webPublicLlms).toBe(rootLlms);
  });

  it("keeps the astro blog index aligned with the live credential-path story", () => {
    expect(astroBlogIndex).toContain("Three credential paths (Rhumb-managed, BYOK, Agent Vault)");
    expect(astroBlogIndex).toContain("Capability-First Agent Onboarding: Managed Superpowers First");
    expect(astroBlogIndex).toContain("The better onboarding model is managed superpowers first, then secure bridges only when needed.");
    expect(astroBlogIndex).not.toContain("Three credential paths (managed, BYOK, Agent Vault)");
    expect(astroBlogIndex).not.toContain("Three credential paths (BYOK, managed, Agent Vault)");
    expect(astroBlogIndex).not.toContain("Three credential modes (BYOK, managed, Agent Vault)");
    expect(astroBlogIndex).not.toContain("Three credential modes (BYOK, managed, x402)");
    expect(astroBlogIndex).not.toContain("Capability-First Agent Onboarding: One Key, Many Superpowers");
    expect(astroBlogIndex).not.toContain("one key, many superpowers");
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
      expect(caps.capabilities.execution.description).toContain("governed API key, wallet-prefund, or x402 per-call, with BYOK or Agent Vault where supported");
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
    expect(pricingExample.data.modes.byok.label).toBe(canonicalPricing.modes.byok.label);
    expect(pricingExample.data.modes.byok.margin_percent).toBe(
      canonicalPricing.modes.byok.margin_percent,
    );
    expect(pricingExample.data.modes.byok.passthrough_note).toBe(
      canonicalPricing.modes.byok.passthrough_note,
    );

    expect(apiDocs).not.toContain("included_executions_per_month");
    expect(apiDocs).not.toContain('"label": "Bring your own key"');
  });
});

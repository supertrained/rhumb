export const PUBLIC_TRUTH = {
  services: 999,
  servicesLabel: "999",
  capabilities: 435,
  capabilitiesLabel: "435",
  categories: 92,
  categoriesLabel: "92",
  callableProviders: 18,
  callableProvidersLabel: "18",
  mcpTools: 21,
  mcpToolsLabel: "21",
  domainsLabel: "50+",
  beachheadLabel: "research, extraction, generation, and narrow enrichment",
  beachheadSummary:
    "Current launchable scope: research, extraction, generation, and narrow enrichment — not general business-agent automation.",
  trustOverviewUrl: "https://rhumb.dev/trust",
  methodologyUrl: "https://rhumb.dev/methodology",
  providersUrl: "https://rhumb.dev/providers",
  routingProofUrl: "https://rhumb.dev/resolve/routing",
  resolveWhatIsUrl: "https://rhumb.dev/resolve/what-is-resolve",
  resolveCompareUrl: "https://rhumb.dev/resolve/compare",
  resolveKeysUrl: "https://rhumb.dev/resolve/keys",
  resolvePricingUrl: "https://rhumb.dev/resolve/per-call-pricing",
  llmsUrl: "https://rhumb.dev/llms.txt",
  publicAgentCapabilitiesUrl: "https://rhumb.dev/.well-known/agent-capabilities.json",
  currentSelfAssessmentUrl: "https://rhumb.dev/blog/we-scored-ourselves",
  historicalSelfAssessmentUrl: "https://rhumb.dev/blog/self-score",
  publicDisputeTemplateUrl:
    "https://github.com/supertrained/rhumb/issues/new?template=score-dispute.md",
  publicDisputesUrl:
    "https://github.com/supertrained/rhumb/issues?q=is%3Aissue+%22Score+dispute%3A%22",
  privateDisputesEmail: "providers@supertrained.ai",
  privateDisputeMailto: "mailto:providers@supertrained.ai?subject=Score%20Dispute",
  disputeResponseSlaBusinessDays: 5,
  catalogRealitySummary:
    "Discovery breadth: 999 scored services and 435 capability definitions. Current runtime-callable surface: 18 callable providers, strongest today for research, extraction, generation, and narrow enrichment.",
  callableRealitySummary:
    "Not every service or capability in the index is executable through Rhumb today. Discovery breadth is wider than current callable coverage.",
  routingPrinciple: "Route by supported capability, runtime factors, and explicit constraints — not leaderboard purity.",
  rhumbEntityShort:
    "Rhumb is an agent gateway that scores external services for AI-agent compatibility and provides governed execution for supported capabilities.",
  rhumbEntityExpanded:
    "Rhumb combines Rhumb Index for scored service discovery with Rhumb Resolve for governed execution. Index ranks the field. Resolve first matches the supported capability path, then routes using AN Score, provider availability / circuit state, estimated cost, credential mode, latency proxy, and policy constraints, or lets the agent pin the supported provider path explicitly.",
  indexShort: "Rhumb Index is free discovery: score, compare, and research services.",
  resolveShort: "Rhumb Resolve is per-call governed execution for supported capabilities.",
  resolveTagline: "One governed surface, many managed capabilities.",
  resolveEntityShort:
    "Rhumb Resolve is Rhumb’s governed execution layer for AI agents: one integration surface for supported capabilities, with managed credentials, explainable routing, optional provider pinning, fallback where a supported alternate is configured, budget controls, and pay-per-call pricing.",
  resolveEntityExpanded:
    "Agents can ask Resolve for a capability or explicitly pin the supported provider path they want. By default, Resolve chooses from providers mapped to that capability, using AN Score as a major input alongside provider availability / circuit state, estimated cost, credential mode, latency proxy, and explicit policy constraints.",
  routingHumanSummary:
    "Resolve routes each call to the best-fit provider for the call by default, while keeping explicit provider choice available when the agent wants direct control.",
  routingMachineSummary:
    "Resolve performs explainable supported-capability routing by first matching the supported capability path, then using AN Score, provider availability / circuit state, estimated cost, credential mode, latency proxy, and explicit policy constraints, while also supporting provider pinning.",
  routingFactors: [
    "supported capability path (candidate filter)",
    "AN Score",
    "provider availability / circuit state",
    "estimated cost",
    "latency proxy",
    "credential mode",
    "policy constraints (pin / allow / deny / cost ceiling)",
  ],
  resolveMentalModel: {
    defaultPath:
      "Default path: start with governed API key or wallet-prefund on `X-Rhumb-Key`, discover a Service, choose a Capability, estimate the call, then execute through Layer 2. One governed surface, many managed capabilities: start with Rhumb-managed capabilities first, bring your systems only when needed, and keep one surface instead of a tool graveyard. Bring BYOK or Agent Vault only when the workflow touches your own systems. Use x402 only when zero-signup per-call matters. Use Layer 1 only when you must pin the provider. Use Layer 3 only when a published recipe already exists.",
    surfaces: [
      {
        name: "REST API",
        summary: "Use direct HTTP when you want explicit endpoint, header, and response control.",
      },
      {
        name: "MCP",
        summary: "Use tools when your agent already speaks MCP and should call Rhumb as a tool provider.",
      },
    ],
    entities: [
      {
        name: "Service",
        summary: "A vendor or product Rhumb evaluates, ranks, and compares.",
      },
      {
        name: "Capability",
        summary: "An executable action like email.send or search.query that can map to multiple Services.",
      },
      {
        name: "Recipe (beta)",
        summary: "A deterministic multi-step workflow compiled on top of Capabilities. Public catalog may still be sparse.",
      },
    ],
    layers: [
      {
        name: "Layer 1",
        summary: "Raw provider access. You pin the provider or tool path yourself.",
      },
      {
        name: "Layer 2",
        summary:
          "Capability routing. Rhumb routes each call to a supported provider using the capability candidate set, runtime factors, and explicit constraints; this is the main production surface today.",
      },
      {
        name: "Layer 3",
        summary: "Deterministic recipes. Real but still beta, with intentionally sparse public inventory.",
      },
    ],
    rails: [
      {
        name: "Discovery",
        summary: "Free, open read path for search, scores, failures, leaderboards, and capability browsing.",
      },
      {
        name: "Governed API key",
        summary: "Account-first execution with managed billing, routing, and dashboard controls.",
      },
      {
        name: "Wallet-prefund",
        summary: "Wallet authenticates once, tops up reusable balance, then executes repeat traffic via X-Rhumb-Key.",
      },
      {
        name: "x402 per-call",
        summary: "Zero-signup per-call USDC payment. Best when autonomous pay-as-you-go matters more than repeat throughput.",
      },
    ],
    credentialModes: [
      {
        name: "BYOK",
        summary: "You bring the upstream credential; Rhumb routes the call without taking custody of your system credential.",
      },
      {
        name: "Rhumb-managed",
        summary: "Rhumb holds the provider credential so the agent can start faster.",
      },
      {
        name: "Agent Vault",
        summary: "Your credential stays encrypted in agent-controlled storage and is injected at execution time.",
      },
    ],
  },
} as const;

export const PUBLIC_TRUTH = {
  services: 1038,
  servicesLabel: "1,038",
  capabilities: 415,
  capabilitiesLabel: "415",
  categories: 92,
  categoriesLabel: "92",
  callableProviders: 16,
  callableProvidersLabel: "16",
  mcpTools: 21,
  mcpToolsLabel: "21",
  domainsLabel: "50+",
  beachheadLabel: "research, extraction, generation, and narrow enrichment",
  beachheadSummary:
    "Current launchable scope: research, extraction, generation, and narrow enrichment — not general business-agent automation.",
  resolveMentalModel: {
    defaultPath:
      "Default path: discover a Service, choose a Capability, estimate the call, then execute through Layer 2 with a governed API key or wallet-prefunded API key. Use x402 only when zero-signup per-call matters. Use Layer 1 only when you must pin the provider. Use Layer 3 only when a published recipe already exists.",
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
        summary: "Raw provider access. You pin the provider yourself.",
      },
      {
        name: "Layer 2",
        summary: "Capability routing. Rhumb picks the best provider and is the main production surface today.",
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
        name: "BYO",
        summary: "You bring the upstream credential; Rhumb routes the call.",
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

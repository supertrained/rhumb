import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { beforeAll, describe, it, expect } from "vitest";
import {
  FindServiceInputSchema,
  GetScoreInputSchema,
  GetAlternativesInputSchema,
  GetFailureModesInputSchema,
  ResolveCapabilityInputSchema,
  ExecuteCapabilityInputSchema,
  EstimateCapabilityInputSchema,
  CheckCredentialsInputSchema,
  TOOL_SCHEMAS,
  TOOL_NAMES,
  type FindServiceInput,
  type FindServiceOutput,
  type GetScoreInput,
  type GetScoreOutput,
  type GetAlternativesInput,
  type GetAlternativesOutput,
  type GetFailureModesInput,
  type GetFailureModesOutput,
  type ResolveCapabilityOutput,
  type EstimateCapabilityOutput
} from "../src/types.js";

const rootReadme = readFileSync(new URL("../../../README.md", import.meta.url), "utf8");
const mcpReadme = readFileSync(new URL("../README.md", import.meta.url), "utf8");
const mcpQuickstartExample = readFileSync(new URL("../../../examples/mcp-quickstart.md", import.meta.url), "utf8");
const examplesReadme = readFileSync(new URL("../../../examples/README.md", import.meta.url), "utf8");
const discoverAndEvaluateExample = readFileSync(new URL("../../../examples/discover-and-evaluate.py", import.meta.url), "utf8");
const resolveAndExecuteExample = readFileSync(new URL("../../../examples/resolve-and-execute.py", import.meta.url), "utf8");
const dogfoodTelemetryExample = readFileSync(new URL("../../../examples/dogfood-telemetry-loop.py", import.meta.url), "utf8");
const budgetAwareRoutingExample = readFileSync(new URL("../../../examples/budget-aware-routing.py", import.meta.url), "utf8");
const rootLlms = readFileSync(new URL("../../../llms.txt", import.meta.url), "utf8");
const webPublicLlms = readFileSync(new URL("../../web/public/llms.txt", import.meta.url), "utf8");
const rootAgentCapabilities = readFileSync(new URL("../../../agent-capabilities.json", import.meta.url), "utf8");
const wellKnownAgentCapabilities = readFileSync(
  new URL("../../astro-web/public/.well-known/agent-capabilities.json", import.meta.url),
  "utf8",
);
const mcpPackageJson = JSON.parse(readFileSync(new URL("../package.json", import.meta.url), "utf8")) as {
  description: string;
  version: string;
};
const mcpServerManifest = JSON.parse(readFileSync(new URL("../server.json", import.meta.url), "utf8")) as {
  description: string;
  version: string;
  packages: Array<{
    version: string;
    environmentVariables: Array<{
      description: string;
      name: string;
    }>;
  }>;
};
const packageRoot = fileURLToPath(new URL("..", import.meta.url));
const npmCommand = process.platform === "win32" ? "npm.cmd" : "npm";

let distServerBundle = "";
let distApiClientBundle = "";
let distTypesBundle = "";

describe("types.contract", () => {
  beforeAll(() => {
    execFileSync(npmCommand, ["run", "build"], { cwd: packageRoot, stdio: "pipe" });
    distServerBundle = readFileSync(new URL("../dist/src/server.js", import.meta.url), "utf8");
    distApiClientBundle = readFileSync(new URL("../dist/src/api-client.js", import.meta.url), "utf8");
    distTypesBundle = readFileSync(new URL("../dist/src/types.js", import.meta.url), "utf8");
  });

  it("all tool schemas are valid JSON Schema objects with required fields", () => {
    for (const [name, schema] of Object.entries(TOOL_SCHEMAS)) {
      expect(schema.type).toBe("object");
      expect(schema.properties).toBeDefined();
      expect(Array.isArray(schema.required)).toBe(true);
      // Some schemas (like discover_capabilities) have no required fields — that's valid
    }
  });

  it("TOOL_NAMES lists all 21 registered tools", () => {
    expect(TOOL_NAMES).toEqual([
      "find_services",
      "get_score",
      "get_alternatives",
      "get_failure_modes",
      "discover_capabilities",
      "resolve_capability",
      "execute_capability",
      "estimate_capability",
      "credential_ceremony",
      "check_credentials",
      "budget",
      "spend",
      "routing",
      "usage_telemetry",
      "check_balance",
      "get_payment_url",
      "get_ledger",
      "rhumb_list_recipes",
      "rhumb_get_recipe",
      "rhumb_recipe_execute",
      "get_receipt"
    ]);
    expect(TOOL_NAMES.length).toBe(21);
  });

  it("execute and estimate schemas use canonical public byok vocabulary", () => {
    expect(ExecuteCapabilityInputSchema.properties.method.description).toContain("byok");
    expect(ExecuteCapabilityInputSchema.properties.method.description).not.toContain("Required for byo (BYOK)");
    expect(ExecuteCapabilityInputSchema.properties.path.description).toContain("byok");
    expect(ExecuteCapabilityInputSchema.properties.credential_mode.description).toContain("'byok'");
    expect(ExecuteCapabilityInputSchema.properties.credential_mode.description).toContain("legacy 'byo' alias still accepted");
    expect(ExecuteCapabilityInputSchema.properties.credential_mode.description).toContain("fall back to byok");
    expect(ExecuteCapabilityInputSchema.properties.credential_mode.description).not.toMatch(/fall back to byo(?:[^k]|$)/);
    expect(ExecuteCapabilityInputSchema.properties.agent_token.description).toContain("byok or agent_vault");
    expect(ExecuteCapabilityInputSchema.properties.x_payment.description).toContain("repeat-traffic X-Rhumb-Key rail");
    expect(ExecuteCapabilityInputSchema.properties.x_payment.description).toContain("governed API key or wallet-prefund");
    expect(ExecuteCapabilityInputSchema.properties.x_payment.description).not.toContain("instead of an API key");
    expect(EstimateCapabilityInputSchema.properties.credential_mode.description).toContain("'byok'");
    expect(EstimateCapabilityInputSchema.properties.credential_mode.description).toContain("legacy 'byo' alias still accepted");
    expect(EstimateCapabilityInputSchema.properties.credential_mode.description).toContain("fall back to byok");
    expect(EstimateCapabilityInputSchema.properties.credential_mode.description).not.toMatch(/fall back to byo(?:[^k]|$)/);
  });

  it("resolve schema names concrete recovery fields and typo recovery", () => {
    expect(ResolveCapabilityInputSchema.properties.capability.description).toContain("recovery_hint.resolve_url");
    expect(ResolveCapabilityInputSchema.properties.capability.description).toContain("recovery_hint.credential_modes_url");
    expect(ResolveCapabilityInputSchema.properties.capability.description).toContain("recovery_hint.alternate_execute_hint");
    expect(ResolveCapabilityInputSchema.properties.capability.description).toContain("recovery_hint.setup_handoff");
    expect(ResolveCapabilityInputSchema.properties.capability.description).toContain("typo recovery");
    expect(ResolveCapabilityInputSchema.properties.capability.description).not.toContain("machine-readable recovery handoffs");
    expect(ResolveCapabilityInputSchema.properties.capability.description).not.toContain("fallback chains.");
    expect(ResolveCapabilityInputSchema.properties.credential_mode?.description).toContain("recovery_hint.resolve_url");
    expect(ResolveCapabilityInputSchema.properties.credential_mode?.description).toContain("recovery_hint.credential_modes_url");
    expect(ResolveCapabilityInputSchema.properties.credential_mode?.description).toContain("recovery_hint.alternate_execute_hint");
    expect(ResolveCapabilityInputSchema.properties.credential_mode?.description).toContain("recovery_hint.setup_handoff");
    expect(ResolveCapabilityInputSchema.properties.credential_mode?.description).not.toContain("machine-readable recovery handoffs");
  });

  it("check_credentials surfaces live readiness globally and per capability", () => {
    expect(CheckCredentialsInputSchema.properties.capability.description).toContain("configured BYOK/direct-bundle readiness");
    expect(CheckCredentialsInputSchema.properties.capability.description).toContain("provider-level mode status");

    expect(rootReadme).toContain("Inspect live credential-mode readiness, globally or for a specific Capability");
    expect(mcpReadme).toContain("| `check_credentials` | Inspect live credential-mode readiness, globally or for a specific Capability |");
    expect(mcpReadme).toContain("call without params for account-wide configured BYOK/direct-bundle readiness");

    expect(distServerBundle).toContain("Call without params to see which BYOK bridges or direct bundles are already configured");
    expect(distServerBundle).toContain("Pass a Capability to inspect provider-level mode status");
    expect(distServerBundle).toContain("Use check_credentials to inspect live readiness globally or for a specific Capability before choosing a rail.");
    expect(distServerBundle).not.toContain("Use check_credentials to see which modes are available.");
    expect(distTypesBundle).toContain("configured BYOK/direct-bundle readiness");
    expect(distTypesBundle).toContain("provider-level mode status");
  });

  it("generated public resolve surfaces describe explicit recovery fields instead of fallback chains", () => {
    for (const surface of [
      rootReadme,
      mcpReadme,
      rootLlms,
      webPublicLlms,
      rootAgentCapabilities,
      wellKnownAgentCapabilities,
    ]) {
      expect(surface).toContain("execute guidance");
      expect(surface).toContain("recovery_hint.resolve_url");
      expect(surface).toContain("recovery_hint.credential_modes_url");
      expect(surface).toContain("recovery_hint.alternate_execute_hint");
      expect(surface).toContain("recovery_hint.setup_handoff");
      expect(surface).not.toContain("machine-readable recovery handoffs");
      expect(surface).not.toContain("fallback chains");
    }

    expect(rootReadme).toContain("Ranked providers + explicit `recovery_hint.*` fields");
    expect(rootReadme).not.toContain("Ranked providers + recovery handoffs");
  });

  it("generated llms, agent capabilities, and MCP metadata stay aligned with the live rail-based execution story", () => {
    for (const surface of [rootLlms, webPublicLlms]) {
      expect(surface).toContain("## Execution (requires a live rail)");
      expect(surface).toContain("## Execution rails");
      expect(surface).toContain("## Operator-controlled credential modes");
      expect(surface).toContain("3 execution rails: governed API key, wallet-prefund, x402 / USDC");
      expect(surface).toContain("2 operator-controlled credential modes where supported: BYOK, Agent Vault");
      expect(surface).toContain("Execution rails: governed API key, wallet-prefund, or x402 per-call");
      expect(surface).toContain("Provider-control modes where supported: BYOK and Agent Vault");
      expect(surface).toContain("Governed API key");
      expect(surface).toContain("Wallet-prefund");
      expect(surface).toContain("x402 / USDC");
      expect(surface).toContain("BYOK credentials");
      expect(surface).toContain("Agent Vault");
      expect(surface).not.toContain("## Auth paths");
      expect(surface).not.toContain("3 credential modes: BYOK, Rhumb-managed, Agent Vault");
      expect(surface).not.toContain("Execution: governed API key, wallet-prefund, x402 per-call, or BYOK");
      expect(surface).not.toContain("## Execution (requires API key or x402 payment)");
    }

    expect(rootReadme).toContain("Default auth for repeat traffic** = governed API key or wallet-prefund on `X-Rhumb-Key`");
    expect(rootReadme).toContain("Bring BYOK or Agent Vault** only when provider control is the point");
    expect(rootReadme).not.toContain("wallet-prefunded API key");

    expect(mcpReadme).toContain("**No governed API key needed for discovery.** Install and start immediately:");
    expect(rootReadme).toContain("Rhumb is an agent gateway for external tools");
    expect(rootReadme).toContain("**Index ranks. Resolve routes.**");
    expect(rootReadme).toContain("### Repository visibility map");
    expect(rootReadme).toContain("Broad discovery is not the same as execution readiness");
    expect(rootReadme).toContain("Resolve chooses the best-fit supported provider for the call");
    expect(rootReadme).not.toContain("Cost-aware routing picks the best provider");
    expect(mcpReadme).toContain("Rhumb scores **999 services** and exposes **435 capability definitions**");
    expect(mcpReadme).toContain("current governed execution is concentrated in **28 callable providers**");
    expect(mcpReadme).toContain("Rhumb routes to the best-fit supported provider for the call");
    expect(mcpReadme).not.toContain("Rhumb picks the best provider");
    expect(mcpReadme).toContain("Default auth for repeat traffic** = governed API key or wallet-prefund on `X-Rhumb-Key`");
    expect(mcpReadme).toContain("Bring BYOK or Agent Vault** only when provider control is the point");
    expect(mcpReadme).toContain("Get a governed API key at https://rhumb.dev/auth/login");
    expect(mcpReadme).not.toContain("1,038 services");
    expect(mcpReadme).not.toContain("415 capability definitions");
    expect(mcpReadme).not.toContain("16 callable providers");
    expect(mcpReadme).not.toContain("wallet-prefunded API key");
    expect(mcpReadme).not.toContain("`RHUMB_API_KEY` via governed account or wallet-prefund");
    expect(mcpReadme).not.toContain("**No API key needed for discovery.** Install and start immediately:");
    expect(mcpReadme).not.toContain("Get a key at https://rhumb.dev/auth/login");

    expect(mcpPackageJson.version).toBe("2.0.0");
    expect(mcpServerManifest.version).toBe("0.8.2");
    expect(mcpServerManifest.packages[0].version).toBe("0.8.2");
    expect(distServerBundle).toContain(`version: "${mcpPackageJson.version}"`);
    expect(distApiClientBundle).toContain(`"User-Agent": "rhumb-mcp/${mcpPackageJson.version}"`);
    expect(distServerBundle).not.toContain("0.8.2");
    expect(distApiClientBundle).not.toContain("rhumb-mcp/0.8");

    expect(mcpServerManifest.packages[0].environmentVariables[0].name).toBe("RHUMB_API_KEY");
    expect(mcpServerManifest.packages[0].environmentVariables[0].description).toContain("Governed API key for authenticated repeat traffic on X-Rhumb-Key");
    expect(mcpServerManifest.packages[0].environmentVariables[0].description).toContain("discovery works without auth");
    expect(mcpServerManifest.packages[0].environmentVariables[0].description).not.toContain("Rhumb API key for authenticated access");
    expect(mcpServerManifest.packages[0].environmentVariables[0].description).not.toContain("execution requires auth or x402 payment");

    expect(mcpQuickstartExample).toContain("For repeat traffic, use governed API key or wallet-prefund on `X-Rhumb-Key`, and bring BYOK or Agent Vault only when provider control is the point.");
    expect(mcpQuickstartExample).toContain("The governed API key is optional — discovery tools work without it. Add it to enable execution.");
    expect(mcpQuickstartExample).toContain("## Get a governed API key");
    expect(mcpQuickstartExample).toContain("Copy your governed API key from the dashboard");
    expect(mcpQuickstartExample).not.toContain("For repeat wallet traffic, use wallet-prefund and then execute with `X-Rhumb-Key`.");
    expect(mcpQuickstartExample).not.toContain("The API key is optional — discovery tools work without it. Add it to enable execution.");
    expect(mcpQuickstartExample).not.toContain("## Get an API key");
    expect(mcpQuickstartExample).not.toContain("Copy your API key from the dashboard");

    expect(examplesReadme).toContain("## Run discovery (no governed API key needed)");
    expect(examplesReadme).toContain("## Run resolve walkthrough (no governed API key needed)");
    expect(examplesReadme).toContain("## Run full execution (governed API key required)");
    expect(examplesReadme).toContain("## Run the dogfood loop (governed API key required)");
    expect(examplesReadme).toContain("Get a governed API key at [rhumb.dev/auth/login](https://rhumb.dev/auth/login).");
    expect(examplesReadme).not.toContain("## Run discovery (no API key needed)");
    expect(examplesReadme).not.toContain("## Run resolve walkthrough (no API key needed)");
    expect(examplesReadme).not.toContain("## Run full execution (API key required)");
    expect(examplesReadme).not.toContain("## Run the dogfood loop (API key required)");
    expect(examplesReadme).not.toContain("Get an API key at [rhumb.dev/auth/login](https://rhumb.dev/auth/login).");

    expect(discoverAndEvaluateExample).toContain("No governed API key needed — all discovery endpoints are public.");
    expect(discoverAndEvaluateExample).not.toContain("No API key needed — all discovery endpoints are public.");

    expect(resolveAndExecuteExample).toContain("RHUMB_API_KEY (your governed API key) is required for estimation and execution.");
    expect(resolveAndExecuteExample).toContain("Set RHUMB_API_KEY (your governed API key) only if you want to continue into estimate and execute.");
    expect(resolveAndExecuteExample).toContain("Set RHUMB_API_KEY (your governed API key) to continue with estimation and execution.");
    expect(resolveAndExecuteExample).toContain("Get a governed API key at https://rhumb.dev/auth/login");
    expect(resolveAndExecuteExample).not.toContain("RHUMB_API_KEY is required for estimation and execution.");
    expect(resolveAndExecuteExample).not.toContain("Set RHUMB_API_KEY only if you want to continue into estimate and execute.");
    expect(resolveAndExecuteExample).not.toContain("Set RHUMB_API_KEY to continue with estimation and execution.");
    expect(resolveAndExecuteExample).not.toContain("Get one at https://rhumb.dev/auth/login");

    expect(dogfoodTelemetryExample).toContain("Set RHUMB_API_KEY (your governed API key) to run the dogfood loop.");
    expect(dogfoodTelemetryExample).toContain("Get a governed API key at https://rhumb.dev/auth/login");
    expect(dogfoodTelemetryExample).toContain("Requires: RHUMB_API_KEY (your governed API key) environment variable.");
    expect(dogfoodTelemetryExample).not.toContain("Set RHUMB_API_KEY to run the dogfood loop.");
    expect(dogfoodTelemetryExample).not.toContain("Requires: RHUMB_API_KEY environment variable.");
    expect(dogfoodTelemetryExample).not.toContain("Get one at https://rhumb.dev/auth/login");

    expect(budgetAwareRoutingExample).toContain("Requires: RHUMB_API_KEY (your governed API key) environment variable.");
    expect(budgetAwareRoutingExample).toContain("Set RHUMB_API_KEY (your governed API key) to run this example.");
    expect(budgetAwareRoutingExample).toContain("Get a governed API key at https://rhumb.dev/auth/login");
    expect(budgetAwareRoutingExample).not.toContain("Requires: RHUMB_API_KEY environment variable.");
    expect(budgetAwareRoutingExample).not.toContain("Set RHUMB_API_KEY to run this example.");
    expect(budgetAwareRoutingExample).not.toContain("Get one at https://rhumb.dev/auth/login");

    for (const surface of [rootAgentCapabilities, wellKnownAgentCapabilities]) {
      expect(surface).toContain('"execution": "rail_based"');
      expect(surface).toContain('"repeat_traffic": "governed_api_key_or_wallet_prefund_on_x_rhumb_key"');
      expect(surface).toContain('"zero_signup": "x402_usdc"');
      expect(surface).toContain('"provider_control": "byok_or_agent_vault"');
      expect(surface).toContain("Execute capabilities through Resolve on the live execution rail returned by resolve: governed API key, wallet-prefund, or x402 per-call, with BYOK or Agent Vault where supported");
      expect(surface).not.toContain('"execution": "api_key_or_x402"');
      expect(surface).not.toContain("Execute capabilities through Resolve with managed auth and cost-aware routing");
    }

    for (const description of [mcpPackageJson.description, mcpServerManifest.description]) {
      expect(description.toLowerCase()).toMatch(/agent-native tool intelligence|agent gateway/);
      expect(description).toContain("governed execution");
      expect(description).toMatch(/Index|Resolve|capability routing/);
      expect(description).not.toMatch(/(?:600\+ services|1000\+ scored services|1,000\+ scored services)/);
    }
  });

  it("published MCP dist bundle stays aligned with explicit resolve recovery wording", () => {
    expect(distServerBundle).toContain("execute guidance");
    expect(distServerBundle).toContain("recovery_hint.resolve_url");
    expect(distServerBundle).toContain("recovery_hint.credential_modes_url");
    expect(distServerBundle).toContain("recovery_hint.alternate_execute_hint");
    expect(distServerBundle).toContain("recovery_hint.setup_handoff");
    expect(distServerBundle).toContain("which provider or recovery handoff should I use?");
    expect(distServerBundle).not.toContain("machine-readable recovery handoffs");
    expect(distServerBundle).not.toContain("fallback chains");
    expect(distServerBundle).not.toContain("which provider or setup step should I use?");

    expect(distTypesBundle).toContain("execute guidance");
    expect(distTypesBundle).toContain("recovery_hint.resolve_url");
    expect(distTypesBundle).toContain("recovery_hint.credential_modes_url");
    expect(distTypesBundle).toContain("recovery_hint.alternate_execute_hint");
    expect(distTypesBundle).toContain("recovery_hint.setup_handoff");
    expect(distTypesBundle).not.toContain("machine-readable recovery handoffs");
    expect(distTypesBundle).not.toContain("fallback chains");
  });

  it("TypeScript types are structurally valid (compile-time + runtime spot check)", () => {
    // These assignments verify the TS types compile correctly.
    // At runtime we spot-check the schemas match expected shapes.

    const findInput: FindServiceInput = { query: "email", limit: 5 };
    expect(findInput.query).toBe("email");

    const findOutput: FindServiceOutput = {
      services: [{ name: "SendGrid", slug: "sendgrid", aggregateScore: 82, executionScore: 85, accessScore: 79, explanation: "Top email API" }]
    };
    expect(findOutput.services).toHaveLength(1);

    const scoreInput: GetScoreInput = { slug: "sendgrid" };
    expect(scoreInput.slug).toBe("sendgrid");

    const scoreOutput: GetScoreOutput = {
      slug: "sendgrid", aggregateScore: 82, executionScore: 85, accessScore: 79,
      confidence: 0.95, tier: "excellent", explanation: "Reliable", freshness: "2026-03-01"
    };
    expect(scoreOutput.tier).toBe("excellent");

    const altInput: GetAlternativesInput = { slug: "sendgrid" };
    expect(altInput.slug).toBe("sendgrid");

    const altOutput: GetAlternativesOutput = {
      alternatives: [{ name: "Mailgun", slug: "mailgun", aggregateScore: 78, reason: "Similar feature set" }]
    };
    expect(altOutput.alternatives).toHaveLength(1);

    const failInput: GetFailureModesInput = { slug: "sendgrid" };
    expect(failInput.slug).toBe("sendgrid");

    const failOutput: GetFailureModesOutput = {
      failures: [{ pattern: "Rate limit", impact: "high", frequency: "occasional", workaround: "Implement backoff" }]
    };
    expect(failOutput.failures).toHaveLength(1);

    expect(ResolveCapabilityInputSchema.properties.credential_mode?.type).toBe("string");

    const resolveOutput: ResolveCapabilityOutput = {
      capability: "email.send",
      providers: [],
      fallbackChain: [],
      relatedBundles: [],
      executeHint: null,
      recoveryHint: {
        reason: "no_execute_ready_providers",
        requestedCredentialMode: "byok",
        resolveUrl: "/v1/capabilities/email.send/resolve",
        credentialModesUrl: "/v1/capabilities/email.send/credential-modes",
        supportedProviderSlugs: ["resend"],
        supportedCredentialModes: ["byok"],
        unavailableProviderSlugs: [],
        notExecuteReadyProviderSlugs: ["resend"],
        alternateExecuteHint: null,
        setupHandoff: {
          preferredProvider: "resend",
          selectionReason: "highest_ranked_provider",
          endpointPattern: null,
          authMethod: "api_key",
          credentialModes: ["byok"],
          configured: false,
          credentialModesUrl: "/v1/capabilities/email.send/credential-modes",
          preferredCredentialMode: "byok",
          fallbackProviders: [],
          setupHint: "Set RHUMB_CREDENTIAL_RESEND_API_KEY environment variable or configure via proxy credentials",
          setupUrl: "/v1/services/resend/ceremony"
        }
      }
    };
    expect(resolveOutput.recoveryHint?.resolveUrl).toBe("/v1/capabilities/email.send/resolve");
    expect(resolveOutput.recoveryHint?.setupHandoff?.setupUrl).toBe("/v1/services/resend/ceremony");

    const estimateOutput: EstimateCapabilityOutput = {
      capabilityId: "workflow_run.list",
      provider: "github",
      credentialMode: "byok",
      costEstimateUsd: null,
      circuitState: "closed",
      endpointPattern: "POST /v2/capabilities/workflow_run.list/execute",
      executeReadiness: {
        status: "auth_required",
        message: "Add X-Rhumb-Key before execute.",
        resolveUrl: "/v2/capabilities/workflow_run.list/resolve",
        credentialModesUrl: "/v2/capabilities/workflow_run.list/credential-modes",
        authHandoff: {
          reason: "auth_required",
          recommendedPath: "governed_api_key",
          retryUrl: "/v2/capabilities/workflow_run.list/execute",
          docsUrl: "/docs#resolve-mental-model",
          paths: [
            {
              kind: "governed_api_key",
              recommended: true,
              setupUrl: "/auth/login",
              retryHeader: "X-Rhumb-Key",
              summary: "Default for most buyers and most repeat agent traffic.",
              requiresHumanSetup: true,
              automaticAfterSetup: true,
              requiresWalletSupport: null,
            },
          ],
        },
      },
    };
    expect(estimateOutput.executeReadiness?.authHandoff?.paths[0]?.retryHeader).toBe("X-Rhumb-Key");
  });
});

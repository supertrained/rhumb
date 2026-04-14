import { readFileSync } from "node:fs";
import { describe, it, expect } from "vitest";
import {
  FindServiceInputSchema,
  GetScoreInputSchema,
  GetAlternativesInputSchema,
  GetFailureModesInputSchema,
  ResolveCapabilityInputSchema,
  ExecuteCapabilityInputSchema,
  EstimateCapabilityInputSchema,
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
  type ResolveCapabilityOutput
} from "../src/types.js";

const rootReadme = readFileSync(new URL("../../../README.md", import.meta.url), "utf8");
const mcpReadme = readFileSync(new URL("../README.md", import.meta.url), "utf8");
const rootLlms = readFileSync(new URL("../../../llms.txt", import.meta.url), "utf8");
const webPublicLlms = readFileSync(new URL("../../web/public/llms.txt", import.meta.url), "utf8");
const rootAgentCapabilities = readFileSync(new URL("../../../agent-capabilities.json", import.meta.url), "utf8");
const wellKnownAgentCapabilities = readFileSync(
  new URL("../../astro-web/public/.well-known/agent-capabilities.json", import.meta.url),
  "utf8",
);

describe("types.contract", () => {
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
    expect(EstimateCapabilityInputSchema.properties.credential_mode.description).toContain("'byok'");
    expect(EstimateCapabilityInputSchema.properties.credential_mode.description).toContain("legacy 'byo' alias still accepted");
    expect(EstimateCapabilityInputSchema.properties.credential_mode.description).toContain("fall back to byok");
    expect(EstimateCapabilityInputSchema.properties.credential_mode.description).not.toMatch(/fall back to byo(?:[^k]|$)/);
  });

  it("resolve schema describes recovery handoffs and typo recovery", () => {
    expect(ResolveCapabilityInputSchema.properties.capability.description).toContain("machine-readable recovery handoffs");
    expect(ResolveCapabilityInputSchema.properties.capability.description).toContain("typo recovery");
    expect(ResolveCapabilityInputSchema.properties.capability.description).not.toContain("fallback chains.");
    expect(ResolveCapabilityInputSchema.properties.credential_mode?.description).toContain("machine-readable recovery handoffs");
  });

  it("generated public resolve surfaces describe execute guidance instead of fallback chains", () => {
    for (const surface of [
      rootReadme,
      mcpReadme,
      rootLlms,
      webPublicLlms,
      rootAgentCapabilities,
      wellKnownAgentCapabilities,
    ]) {
      expect(surface).toContain("execute guidance");
      expect(surface).toContain("machine-readable recovery handoffs");
      expect(surface).not.toContain("fallback chains");
    }
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
  });
});

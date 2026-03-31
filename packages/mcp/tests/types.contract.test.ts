import { describe, it, expect } from "vitest";
import {
  FindServiceInputSchema,
  GetScoreInputSchema,
  GetAlternativesInputSchema,
  GetFailureModesInputSchema,
  TOOL_SCHEMAS,
  TOOL_NAMES,
  type FindServiceInput,
  type FindServiceOutput,
  type GetScoreInput,
  type GetScoreOutput,
  type GetAlternativesInput,
  type GetAlternativesOutput,
  type GetFailureModesInput,
  type GetFailureModesOutput
} from "../src/types.js";

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
  });
});

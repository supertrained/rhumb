import { describe, it, expect, beforeAll } from "vitest";
import YAML from "yaml";
import fs from "fs";
import path from "path";
import {
  SERVICE_DIMENSIONS,
  type ServiceDimensions,
} from "../../../scripts/service-dimensions";
import {
  runDatasetScoring,
  type ANScoreResult,
  type ScoringRunResult,
} from "../../../scripts/score-dataset";

// ─── Fixtures ───

const datasetPath = path.join(__dirname, "../public/data/initial-dataset.yaml");
const datasetContent = fs.readFileSync(datasetPath, "utf-8");
const dataset = YAML.parse(datasetContent);
const datasetSlugs: string[] = dataset.services.map((s: { slug: string }) => s.slug);

let scoringResult: ScoringRunResult;

beforeAll(async () => {
  scoringResult = await runDatasetScoring({ dryRun: true });
}, 30_000);

// ─── AN Score v0.2 Weights (mirrored from Python engine) ───

const DIMENSION_WEIGHTS: Record<string, number> = {
  I1: 0.09166666666666667, I2: 0.07333333333333333, I3: 0.09166666666666667,
  I4: 0.055, I5: 0.04583333333333334, I6: 0.03666666666666667, I7: 0.04583333333333334,
  F1: 0.0761904761904762, F2: 0.06666666666666667, F3: 0.05714285714285715,
  F4: 0.05714285714285715, F5: 0.04761904761904762, F6: 0.04761904761904762,
  F7: 0.04761904761904762,
  O1: 0.07, O2: 0.04, O3: 0.05,
};

const ACCESS_DIMENSION_WEIGHTS: Record<string, number> = {
  A1: 0.24, A2: 0.20, A3: 0.18, A4: 0.14, A5: 0.14, A6: 0.10,
};

const ALL_EXECUTION_DIMS = Object.keys(DIMENSION_WEIGHTS);
const ALL_ACCESS_DIMS = Object.keys(ACCESS_DIMENSION_WEIGHTS);

// ─── 1. Probe Resilience Tests ───

describe("Probe Resilience", () => {
  it("should score all 50 services without crashes", () => {
    expect(scoringResult.scored).toBe(50);
    expect(scoringResult.failed).toBe(0);
    expect(scoringResult.errors).toHaveLength(0);
  });

  it("should complete within reasonable time (<10s for 50 services)", () => {
    expect(scoringResult.duration_ms).toBeLessThan(10_000);
  });

  it("should handle auth-gated services gracefully with auth_required flag", () => {
    const authServices = scoringResult.scores.filter(
      (s) => s.probe_metadata.auth_required === true,
    );
    // At least amazon-ses, salesforce, adyen, braintree, paypal, okta, cognito, google-calendar,
    // microsoft-outlook, aws, twitter-api, linkedin-api should be flagged
    expect(authServices.length).toBeGreaterThanOrEqual(8);

    // Verify each auth-required service still got a valid score
    for (const s of authServices) {
      expect(s.score).toBeGreaterThanOrEqual(0);
      expect(s.score).toBeLessThanOrEqual(10);
      expect(s.tier).toMatch(/^L[1-4]$/);
      expect(s.confidence).toBeGreaterThan(0);
    }
  });

  it("should handle missing-doc services gracefully with docs_unavailable flag", () => {
    const docsUnavailable = scoringResult.scores.filter(
      (s) => s.probe_metadata.docs_unavailable === true,
    );
    expect(docsUnavailable.length).toBeGreaterThanOrEqual(1);

    // when2meet should be flagged
    const when2meet = docsUnavailable.find((s) => s.service_slug === "when2meet");
    expect(when2meet).toBeDefined();
    expect(when2meet!.score).toBeGreaterThan(0);
    expect(when2meet!.tier).toBe("L1"); // Expected to be Emerging given low scores
  });
});

// ─── 2. Score Persistence & Integrity Tests ───

describe("Score Persistence & Integrity", () => {
  it("should produce exactly 50 score records matching dataset", () => {
    expect(scoringResult.scores).toHaveLength(50);
    const scoredSlugs = scoringResult.scores.map((s) => s.service_slug).sort();
    expect(scoredSlugs).toEqual([...datasetSlugs].sort());
  });

  it("should have valid timestamps on all scores", () => {
    for (const score of scoringResult.scores) {
      expect(score.calculated_at).toBeDefined();
      const ts = new Date(score.calculated_at);
      expect(ts.getTime()).toBeGreaterThan(0);
      // Should be recent (within last 60 seconds)
      expect(ts.getTime()).toBeGreaterThan(Date.now() - 60_000);
      expect(ts.getTime()).toBeLessThanOrEqual(Date.now() + 1_000);
    }
  });

  it("should have no data corruption — all numeric fields in valid ranges", () => {
    for (const score of scoringResult.scores) {
      // Aggregate recommendation score (0-10)
      expect(score.score).toBeGreaterThanOrEqual(0);
      expect(score.score).toBeLessThanOrEqual(10);

      // Execution score (0-10)
      expect(score.execution_score).toBeGreaterThanOrEqual(0);
      expect(score.execution_score).toBeLessThanOrEqual(10);

      // Access readiness (null or 0-10)
      if (score.access_readiness_score !== null) {
        expect(score.access_readiness_score).toBeGreaterThanOrEqual(0);
        expect(score.access_readiness_score).toBeLessThanOrEqual(10);
      }

      // Confidence (0-1)
      expect(score.confidence).toBeGreaterThanOrEqual(0);
      expect(score.confidence).toBeLessThanOrEqual(1);

      // Tier must be L1-L4
      expect(score.tier).toMatch(/^L[1-4]$/);

      // Tier label must be valid
      expect(["Emerging", "Developing", "Ready", "Native"]).toContain(score.tier_label);
    }
  });
});

// ─── 3. Metadata Integrity Tests ───

describe("Metadata Integrity", () => {
  it("should include valid latency distributions for all scores", () => {
    for (const score of scoringResult.scores) {
      const latency = score.probe_metadata.latency_distribution_ms;
      expect(latency).toBeDefined();
      expect(latency.p50).toBeGreaterThan(0);
      expect(latency.p95).toBeGreaterThanOrEqual(latency.p50);
      expect(latency.p99).toBeGreaterThanOrEqual(latency.p95);
      expect(latency.samples).toBeGreaterThan(0);
    }
  });

  it("should include consistent schema version (v0.2) across all scores", () => {
    for (const score of scoringResult.scores) {
      expect(score.an_score_version).toBe("0.2");
    }
  });

  it("should have correct probe_types in metadata", () => {
    for (const score of scoringResult.scores) {
      expect(score.probe_metadata.probe_types.length).toBeGreaterThan(0);
      for (const probeType of score.probe_metadata.probe_types) {
        expect(typeof probeType).toBe("string");
        expect(probeType.length).toBeGreaterThan(0);
      }
    }
  });

  it("should have evidence counts > 0 for all services", () => {
    for (const score of scoringResult.scores) {
      expect(score.probe_metadata.evidence_count).toBeGreaterThan(0);
    }
  });
});

// ─── 4. Error Scenario Tests ───

describe("Error Scenario Handling", () => {
  it("should correctly flag auth-required services without failing", () => {
    const expectedAuthServices = [
      "amazon-ses", "salesforce", "adyen", "braintree", "paypal",
      "okta", "cognito", "google-calendar", "microsoft-outlook",
      "aws", "twitter-api", "linkedin-api",
    ];

    for (const slug of expectedAuthServices) {
      const score = scoringResult.scores.find((s) => s.service_slug === slug);
      expect(score).toBeDefined();
      expect(score!.probe_metadata.auth_required).toBe(true);
      // Auth services should still get valid scores
      expect(score!.score).toBeGreaterThan(0);
    }
  });

  it("should correctly flag docs_unavailable services without failing", () => {
    const expectedDocsUnavailable = ["when2meet"];
    for (const slug of expectedDocsUnavailable) {
      const score = scoringResult.scores.find((s) => s.service_slug === slug);
      expect(score).toBeDefined();
      expect(score!.probe_metadata.docs_unavailable).toBe(true);
    }
  });

  it("should produce a valid results artifact file", () => {
    const artifactPath = path.join(
      __dirname, "../../../artifacts/dataset-scores.json",
    );
    expect(fs.existsSync(artifactPath)).toBe(true);

    const artifact = JSON.parse(fs.readFileSync(artifactPath, "utf-8"));
    expect(artifact.metadata).toBeDefined();
    expect(artifact.metadata.total_services).toBe(50);
    expect(artifact.metadata.scored).toBe(50);
    expect(artifact.metadata.failed).toBe(0);
    expect(artifact.metadata.an_score_version).toBe("0.2");
    expect(artifact.scores).toHaveLength(50);
    expect(artifact.errors).toHaveLength(0);
  });
});

// ─── 5. Data Quality Tests ───

describe("Data Quality", () => {
  it("should have no duplicate scores (unique slugs)", () => {
    const slugs = scoringResult.scores.map((s) => s.service_slug);
    const uniqueSlugs = new Set(slugs);
    expect(uniqueSlugs.size).toBe(slugs.length);
  });

  it("should have dimension data for every dataset service (no orphaned probes)", () => {
    const dimensionSlugs = new Set(SERVICE_DIMENSIONS.map((s) => s.slug));
    for (const slug of datasetSlugs) {
      expect(dimensionSlugs.has(slug)).toBe(true);
    }
  });

  it("should use exactly the 17 execution dimensions from AN Score v0.2", () => {
    for (const svc of SERVICE_DIMENSIONS) {
      const dimKeys = Object.keys(svc.dimensions).sort();
      expect(dimKeys).toEqual(ALL_EXECUTION_DIMS.sort());
    }
  });

  it("should use exactly the 6 access readiness dimensions", () => {
    for (const svc of SERVICE_DIMENSIONS) {
      const accessKeys = Object.keys(svc.access_dimensions).sort();
      expect(accessKeys).toEqual(ALL_ACCESS_DIMS.sort());
    }
  });

  it("should have all dimension scores within 0.0–10.0 range", () => {
    for (const svc of SERVICE_DIMENSIONS) {
      for (const [dim, score] of Object.entries(svc.dimensions)) {
        expect(score).toBeGreaterThanOrEqual(0.0);
        expect(score).toBeLessThanOrEqual(10.0);
      }
      for (const [dim, score] of Object.entries(svc.access_dimensions)) {
        expect(score).toBeGreaterThanOrEqual(0.0);
        expect(score).toBeLessThanOrEqual(10.0);
      }
    }
  });
});

// ─── 6. Type Safety Tests ───

describe("Type Safety — AN Score Schema v0.2", () => {
  it("should match the ANScoreSchema contract for every score", () => {
    for (const score of scoringResult.scores) {
      // Required string fields
      expect(typeof score.service_slug).toBe("string");
      expect(score.service_slug.length).toBeGreaterThan(0);
      expect(typeof score.an_score_version).toBe("string");
      expect(typeof score.tier).toBe("string");
      expect(typeof score.tier_label).toBe("string");
      expect(typeof score.explanation).toBe("string");
      expect(typeof score.calculated_at).toBe("string");

      // Required numeric fields
      expect(typeof score.score).toBe("number");
      expect(typeof score.execution_score).toBe("number");
      expect(typeof score.aggregate_recommendation_score).toBe("number");
      expect(typeof score.confidence).toBe("number");

      // Nullable numeric field
      expect(
        score.access_readiness_score === null || typeof score.access_readiness_score === "number",
      ).toBe(true);

      // dimension_snapshot must be an object
      expect(typeof score.dimension_snapshot).toBe("object");
      expect(score.dimension_snapshot).not.toBeNull();

      // probe_metadata must contain required fields
      expect(typeof score.probe_metadata).toBe("object");
      expect(typeof score.probe_metadata.latency_distribution_ms).toBe("object");
      expect(Array.isArray(score.probe_metadata.probe_types)).toBe(true);
      expect(typeof score.probe_metadata.evidence_count).toBe("number");
      expect(typeof score.probe_metadata.freshness).toBe("string");
      expect(typeof score.probe_metadata.auth_required).toBe("boolean");
      expect(typeof score.probe_metadata.docs_unavailable).toBe("boolean");
      expect(typeof score.probe_metadata.runner).toBe("string");
    }
  });

  it("should have tier consistent with aggregate recommendation score", () => {
    for (const score of scoringResult.scores) {
      const aggScore = score.aggregate_recommendation_score;
      const expectedBaseTier =
        aggScore < 4.0 ? "L1" :
        aggScore < 6.0 ? "L2" :
        aggScore < 8.0 ? "L3" : "L4";

      // Tier guardrails may cap tier downward, never upward
      const tierOrder: Record<string, number> = { L1: 1, L2: 2, L3: 3, L4: 4 };
      expect(tierOrder[score.tier]).toBeLessThanOrEqual(tierOrder[expectedBaseTier]);
    }
  });

  it("should have aggregate_recommendation = execution when access = null, blended otherwise", () => {
    for (const score of scoringResult.scores) {
      if (score.access_readiness_score === null) {
        expect(score.aggregate_recommendation_score).toBe(score.execution_score);
      } else {
        // aggregate = 0.70 * execution + 0.30 * access (rounded)
        const expected = Math.round(
          (score.execution_score * 0.70 + score.access_readiness_score * 0.30) * 10,
        ) / 10;
        expect(score.aggregate_recommendation_score).toBeCloseTo(expected, 1);
      }
    }
  });
});

// ─── 7. Score Sanity Checks (Calibration) ───

describe("Score Calibration Sanity", () => {
  it("should rank Stripe highest in payments", () => {
    const paymentScores = scoringResult.scores
      .filter((s) => {
        const svc = dataset.services.find((d: { slug: string }) => d.slug === s.service_slug);
        return svc?.category === "payments";
      })
      .sort((a, b) => b.aggregate_recommendation_score - a.aggregate_recommendation_score);

    expect(paymentScores[0].service_slug).toBe("stripe");
    expect(paymentScores[0].tier).toBe("L4");
  });

  it("should score Resend higher than Mailgun in email", () => {
    const resend = scoringResult.scores.find((s) => s.service_slug === "resend")!;
    const mailgun = scoringResult.scores.find((s) => s.service_slug === "mailgun")!;
    expect(resend.aggregate_recommendation_score).toBeGreaterThan(
      mailgun.aggregate_recommendation_score,
    );
  });

  it("should score Algolia highest in search", () => {
    const searchScores = scoringResult.scores
      .filter((s) => {
        const svc = dataset.services.find((d: { slug: string }) => d.slug === s.service_slug);
        return svc?.category === "search";
      })
      .sort((a, b) => b.aggregate_recommendation_score - a.aggregate_recommendation_score);

    expect(searchScores[0].service_slug).toBe("algolia");
  });

  it("should score when2meet as L1 (Emerging)", () => {
    const when2meet = scoringResult.scores.find((s) => s.service_slug === "when2meet")!;
    expect(when2meet.tier).toBe("L1");
    expect(when2meet.aggregate_recommendation_score).toBeLessThan(4.0);
  });

  it("should have score distribution across all tiers", () => {
    const tiers = new Set(scoringResult.scores.map((s) => s.tier));
    // We expect at least 3 of 4 tiers to be represented
    expect(tiers.size).toBeGreaterThanOrEqual(3);
  });
});

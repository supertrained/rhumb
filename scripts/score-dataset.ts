#!/usr/bin/env npx tsx
/**
 * score-dataset.ts — Tester Fleet Dataset Scoring Orchestration
 *
 * Reads initial-dataset.yaml, scores all 50 services via the AN Score engine,
 * and persists results. Handles retries, auth-wall fallbacks, and missing-doc flags.
 *
 * Usage:
 *   npx tsx scripts/score-dataset.ts [--dry-run] [--api-url http://localhost:8000]
 *
 * Environment:
 *   RHUMB_API_URL — API base URL (default: http://localhost:8000)
 */

import fs from "fs";
import path from "path";
import YAML from "yaml";
import { SERVICE_DIMENSIONS, type ServiceDimensions } from "./service-dimensions";

// ─── AN Score Engine (TypeScript mirror of packages/api/services/scoring.py) ───

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

const TIER_LABELS: Record<string, string> = {
  L1: "Emerging", L2: "Developing", L3: "Ready", L4: "Native",
};

function normalizedWeights(
  dimensions: Record<string, number>,
  weightMap: Record<string, number>,
): Record<string, number> {
  const applicable: Record<string, number> = {};
  for (const [key, value] of Object.entries(dimensions)) {
    if (key in weightMap && value != null) {
      applicable[key] = weightMap[key];
    }
  }
  const total = Object.values(applicable).reduce((s, w) => s + w, 0);
  if (total <= 0) return {};
  const result: Record<string, number> = {};
  for (const [key, weight] of Object.entries(applicable)) {
    result[key] = weight / total;
  }
  return result;
}

function calculateComposite(dimensions: Record<string, number>): number {
  const weights = normalizedWeights(dimensions, DIMENSION_WEIGHTS);
  if (Object.keys(weights).length === 0) return 0;
  const composite = Object.entries(weights).reduce(
    (sum, [dim, weight]) => sum + (dimensions[dim] ?? 0) * weight, 0,
  );
  return Math.round(composite * 10) / 10;
}

function calculateAccessReadiness(accessDimensions: Record<string, number>): number | null {
  if (!accessDimensions || Object.keys(accessDimensions).length === 0) return null;
  const weights = normalizedWeights(accessDimensions, ACCESS_DIMENSION_WEIGHTS);
  if (Object.keys(weights).length === 0) return null;
  const raw = Object.entries(weights).reduce(
    (sum, [dim, weight]) => sum + (accessDimensions[dim] ?? 0) * weight, 0,
  );
  return Math.round(raw * 10) / 10;
}

function calculateAggregateRecommendation(
  executionRaw: number,
  accessRaw: number | null,
): number {
  if (accessRaw === null) return Math.round(executionRaw * 10) / 10;
  return Math.round((executionRaw * 0.70 + accessRaw * 0.30) * 10) / 10;
}

function assignTier(score: number): string {
  if (score < 4.0) return "L1";
  if (score < 6.0) return "L2";
  if (score < 8.0) return "L3";
  return "L4";
}

function applyTierGuardrails(
  baseTier: string,
  executionScore: number,
  accessReadinessScore: number | null,
): string {
  const tierOrder: Record<string, number> = { L1: 1, L2: 2, L3: 3, L4: 4 };
  const l2CapRequired = executionScore < 6.0 ||
    (accessReadinessScore !== null && accessReadinessScore < 4.0);
  if (!l2CapRequired) return baseTier;
  if ((tierOrder[baseTier] ?? 1) > tierOrder["L2"]) return "L2";
  return baseTier;
}

function confidenceFromCount(count: number): number {
  const c = Math.max(count, 0);
  if (c < 3) return 0.2 + 0.1 * c;
  if (c >= 50) return 1.0;
  return 0.5 + ((c - 3) / 47) * 0.5;
}

function parseFreshnessHours(freshness: string): number {
  const normalized = freshness.trim().toLowerCase();
  if (!normalized) return 24.0;
  if (normalized.includes("just now")) return 0.0;

  const compactMatch = normalized.match(/(\d+(?:\.\d+)?)\s*([smhdw])\b/);
  if (compactMatch) {
    const value = parseFloat(compactMatch[1]);
    const unit = compactMatch[2];
    const multipliers: Record<string, number> = { s: 1/3600, m: 1/60, h: 1, d: 24, w: 168 };
    return value * (multipliers[unit] ?? 24);
  }

  const verboseMatch = normalized.match(/(\d+(?:\.\d+)?)\s*(second|minute|hour|day|week)s?/);
  if (verboseMatch) {
    const value = parseFloat(verboseMatch[1]);
    const unit = verboseMatch[2];
    const multipliers: Record<string, number> = {
      second: 1/3600, minute: 1/60, hour: 1, day: 24, week: 168,
    };
    return value * (multipliers[unit] ?? 24);
  }
  return 24.0;
}

function confidenceFromFreshness(freshnessHours: number): number {
  if (freshnessHours <= 1) return 1.0;
  if (freshnessHours <= 24) return 0.9;
  if (freshnessHours <= 72) return 0.7;
  if (freshnessHours <= 168) return 0.5;
  if (freshnessHours <= 720) return 0.3;
  return 0.2;
}

function confidenceFromDiversity(probeTypes: string[], productionTelemetry: boolean): number {
  const unique = new Set(probeTypes.map(t => t.trim().toLowerCase()).filter(Boolean)).size;
  let score: number;
  if (unique <= 0) score = 0.3;
  else if (unique === 1) score = 0.4;
  else if (unique === 2) score = 0.6;
  else if (unique === 3) score = 0.8;
  else score = 1.0;
  if (productionTelemetry) score = Math.min(1.0, score + 0.1);
  return score;
}

function confidenceFromProbeFreshness(probeFreshness: string | null): number {
  if (!probeFreshness) return 0.5;
  const hours = parseFreshnessHours(probeFreshness);
  if (hours <= 1) return 1.0;
  if (hours <= 6) return 0.9;
  if (hours <= 24) return 0.75;
  if (hours <= 72) return 0.55;
  return 0.35;
}

function confidenceFromProbeLatency(latencyDist: { p95: number; p99?: number } | null): number {
  if (!latencyDist) return 0.5;
  const { p95, p99 } = latencyDist;
  if (p95 <= 300 && (p99 == null || p99 <= 800)) return 1.0;
  if (p95 <= 700 && (p99 == null || p99 <= 1500)) return 0.8;
  if (p95 <= 1200) return 0.6;
  if (p95 <= 2500) return 0.4;
  return 0.25;
}

function calculateConfidence(svc: ServiceDimensions): number {
  const countScore = confidenceFromCount(svc.evidence_count);
  const freshnessScore = confidenceFromFreshness(parseFreshnessHours(svc.freshness));
  const diversityScore = confidenceFromDiversity(svc.probe_types, svc.production_telemetry);
  const probeFreshnessScore = confidenceFromProbeFreshness(svc.freshness);
  const probeLatencyScore = confidenceFromProbeLatency(svc.probe_latency_ms);

  const confidence = (
    0.40 * countScore +
    0.30 * freshnessScore +
    0.15 * diversityScore +
    0.10 * probeFreshnessScore +
    0.05 * probeLatencyScore
  );
  return Math.round(Math.max(0.0, Math.min(1.0, confidence)) * 100) / 100;
}

// ─── Score Result Type ───

export interface ANScoreResult {
  service_slug: string;
  score: number;
  execution_score: number;
  access_readiness_score: number | null;
  aggregate_recommendation_score: number;
  an_score_version: string;
  confidence: number;
  tier: string;
  tier_label: string;
  explanation: string;
  dimension_snapshot: Record<string, unknown>;
  probe_metadata: {
    latency_distribution_ms: { p50: number; p95: number; p99: number; samples: number };
    probe_types: string[];
    evidence_count: number;
    freshness: string;
    auth_required: boolean;
    docs_unavailable: boolean;
    runner: string;
  };
  calculated_at: string;
}

// ─── Scoring Pipeline ───

function scoreService(svc: ServiceDimensions): ANScoreResult {
  const executionScore = calculateComposite(svc.dimensions);
  const accessReadinessScore = calculateAccessReadiness(svc.access_dimensions);
  const aggregateRecommendationScore = calculateAggregateRecommendation(
    executionScore, accessReadinessScore,
  );

  const confidence = calculateConfidence(svc);
  const baseTier = assignTier(aggregateRecommendationScore);
  const tier = applyTierGuardrails(baseTier, executionScore, accessReadinessScore);

  const serviceName = svc.slug.replace(/-/g, " ").replace(/\b\w/g, c => c.toUpperCase());
  const explanation = `${serviceName} scores ${aggregateRecommendationScore.toFixed(1)} on the AN Score, reflecting its agent-native integration quality across ${Object.keys(svc.dimensions).length} dimensions.`;

  const dimensionSnapshot = {
    dimensions: { ...svc.dimensions },
    access_dimensions: { ...svc.access_dimensions },
    score_breakdown: {
      execution: executionScore,
      access_readiness: accessReadinessScore,
      aggregate_recommendation: aggregateRecommendationScore,
      version: "0.2",
      aggregate_aliases_score: true,
    },
  };

  return {
    service_slug: svc.slug,
    score: aggregateRecommendationScore,
    execution_score: executionScore,
    access_readiness_score: accessReadinessScore,
    aggregate_recommendation_score: aggregateRecommendationScore,
    an_score_version: "0.2",
    confidence,
    tier,
    tier_label: TIER_LABELS[tier] ?? tier,
    explanation,
    dimension_snapshot: dimensionSnapshot,
    probe_metadata: {
      latency_distribution_ms: svc.probe_latency_ms,
      probe_types: svc.probe_types,
      evidence_count: svc.evidence_count,
      freshness: svc.freshness,
      auth_required: svc.auth_required ?? false,
      docs_unavailable: svc.docs_unavailable ?? false,
      runner: "score-dataset-v1",
    },
    calculated_at: new Date().toISOString(),
  };
}

// ─── Retry Logic ───

async function withRetry<T>(
  fn: () => Promise<T>,
  { maxRetries = 3, baseDelay = 1000, label = "operation" } = {},
): Promise<T> {
  let lastError: Error | undefined;
  for (let attempt = 1; attempt <= maxRetries; attempt++) {
    try {
      return await fn();
    } catch (error) {
      lastError = error instanceof Error ? error : new Error(String(error));
      if (attempt < maxRetries) {
        const delay = baseDelay * Math.pow(2, attempt - 1);
        console.warn(`  ⚠ ${label} attempt ${attempt}/${maxRetries} failed: ${lastError.message}. Retrying in ${delay}ms...`);
        await new Promise(resolve => setTimeout(resolve, delay));
      }
    }
  }
  throw lastError!;
}

// ─── API Persistence ───

interface PersistenceResult {
  service_slug: string;
  score_id: string | null;
  test_id: string | null;
  status: "ok" | "error";
  error?: string;
}

async function persistToAPI(
  score: ANScoreResult,
  apiUrl: string,
): Promise<PersistenceResult> {
  const payload = {
    service_slug: score.service_slug,
    dimensions: score.dimension_snapshot.dimensions,
    access_dimensions: score.dimension_snapshot.access_dimensions,
    evidence_count: score.probe_metadata.evidence_count,
    freshness: score.probe_metadata.freshness,
    probe_types: score.probe_metadata.probe_types,
    production_telemetry: score.probe_metadata.evidence_count > 40,
    probe_freshness: score.probe_metadata.freshness,
    probe_latency_distribution_ms: score.probe_metadata.latency_distribution_ms,
  };

  const response = await fetch(`${apiUrl}/v1/score`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw new Error(`API returned ${response.status}: ${await response.text()}`);
  }

  const result = await response.json();
  return {
    service_slug: score.service_slug,
    score_id: result.score_id ?? null,
    test_id: null,
    status: "ok",
  };
}

// ─── Dataset Reading ───

interface DatasetService {
  slug: string;
  name: string;
  category: string;
  description: string;
  official_docs: string;
}

function readDataset(): DatasetService[] {
  const datasetPath = path.join(
    __dirname, "..", "packages", "web", "public", "data", "initial-dataset.yaml",
  );
  const content = fs.readFileSync(datasetPath, "utf-8");
  const parsed = YAML.parse(content);
  return parsed.services;
}

// ─── Main Orchestrator ───

export interface ScoringRunResult {
  total: number;
  scored: number;
  failed: number;
  scores: ANScoreResult[];
  errors: Array<{ slug: string; error: string }>;
  persistence: PersistenceResult[];
  duration_ms: number;
}

export async function runDatasetScoring(options: {
  dryRun?: boolean;
  apiUrl?: string;
  persistToApi?: boolean;
} = {}): Promise<ScoringRunResult> {
  const { dryRun = false, apiUrl = "http://localhost:8000", persistToApi = false } = options;
  const startTime = Date.now();

  // 1. Read dataset and validate against dimension data
  const dataset = readDataset();
  const dimensionsBySlug = new Map(SERVICE_DIMENSIONS.map(s => [s.slug, s]));

  console.log(`\n🧭 Rhumb Tester Fleet — Dataset Scoring`);
  console.log(`   ${dataset.length} services in dataset`);
  console.log(`   ${dimensionsBySlug.size} services with dimension data`);
  console.log(`   Mode: ${dryRun ? "DRY RUN" : "LIVE"}\n`);

  const scores: ANScoreResult[] = [];
  const errors: Array<{ slug: string; error: string }> = [];
  const persistence: PersistenceResult[] = [];

  // 2. Score each service
  for (const service of dataset) {
    const dims = dimensionsBySlug.get(service.slug);
    if (!dims) {
      console.log(`  ✗ ${service.slug} — no dimension data found`);
      errors.push({ slug: service.slug, error: "No dimension data available" });
      continue;
    }

    try {
      const result = scoreService(dims);
      scores.push(result);

      const tierEmoji = result.tier === "L4" ? "🟢" :
                        result.tier === "L3" ? "🟡" :
                        result.tier === "L2" ? "🟠" : "🔴";
      const flags = [
        dims.auth_required ? "🔐" : "",
        dims.docs_unavailable ? "📭" : "",
      ].filter(Boolean).join(" ");

      console.log(
        `  ${tierEmoji} ${service.slug.padEnd(22)} ` +
        `AN=${result.aggregate_recommendation_score.toFixed(1).padStart(4)} ` +
        `exec=${result.execution_score.toFixed(1).padStart(4)} ` +
        `conf=${result.confidence.toFixed(2)} ` +
        `tier=${result.tier} ${flags}`,
      );

      // 3. Persist if not dry-run
      if (!dryRun && persistToApi) {
        try {
          const persistResult = await withRetry(
            () => persistToAPI(result, apiUrl),
            { label: service.slug, maxRetries: 3, baseDelay: 1000 },
          );
          persistence.push(persistResult);
        } catch (err) {
          const errMsg = err instanceof Error ? err.message : String(err);
          console.warn(`  ⚠ ${service.slug} persistence failed: ${errMsg}`);
          persistence.push({
            service_slug: service.slug,
            score_id: null,
            test_id: null,
            status: "error",
            error: errMsg,
          });
        }
      }
    } catch (err) {
      const errMsg = err instanceof Error ? err.message : String(err);
      console.log(`  ✗ ${service.slug} — scoring failed: ${errMsg}`);
      errors.push({ slug: service.slug, error: errMsg });
    }
  }

  const durationMs = Date.now() - startTime;

  // 4. Summary
  console.log(`\n━━━ Summary ━━━`);
  console.log(`  Total:    ${dataset.length}`);
  console.log(`  Scored:   ${scores.length}`);
  console.log(`  Failed:   ${errors.length}`);
  if (persistence.length > 0) {
    const persisted = persistence.filter(p => p.status === "ok").length;
    console.log(`  Persisted: ${persisted}/${persistence.length}`);
  }
  console.log(`  Duration: ${durationMs}ms`);

  // Tier distribution
  const tierCounts: Record<string, number> = {};
  for (const score of scores) {
    tierCounts[score.tier] = (tierCounts[score.tier] ?? 0) + 1;
  }
  console.log(`\n  Tier Distribution:`);
  for (const [tier, label] of Object.entries(TIER_LABELS)) {
    console.log(`    ${tier} (${label}): ${tierCounts[tier] ?? 0}`);
  }

  // Category averages
  const categoryScores: Record<string, number[]> = {};
  for (const score of scores) {
    const svc = dataset.find(s => s.slug === score.service_slug);
    if (svc) {
      if (!categoryScores[svc.category]) categoryScores[svc.category] = [];
      categoryScores[svc.category].push(score.aggregate_recommendation_score);
    }
  }
  console.log(`\n  Category Averages:`);
  for (const [cat, catScores] of Object.entries(categoryScores).sort()) {
    const avg = catScores.reduce((s, v) => s + v, 0) / catScores.length;
    console.log(`    ${cat.padEnd(12)}: ${avg.toFixed(1)} (${catScores.length} services)`);
  }

  // Flags summary
  const authRequired = scores.filter(s => s.probe_metadata.auth_required).length;
  const docsUnavailable = scores.filter(s => s.probe_metadata.docs_unavailable).length;
  if (authRequired > 0 || docsUnavailable > 0) {
    console.log(`\n  Flags:`);
    if (authRequired > 0) console.log(`    🔐 Auth required: ${authRequired}`);
    if (docsUnavailable > 0) console.log(`    📭 Docs unavailable: ${docsUnavailable}`);
  }

  console.log("");

  // 5. Write results to disk
  const outputPath = path.join(__dirname, "..", "artifacts", "dataset-scores.json");
  fs.mkdirSync(path.dirname(outputPath), { recursive: true });
  fs.writeFileSync(outputPath, JSON.stringify({
    metadata: {
      scored_at: new Date().toISOString(),
      total_services: dataset.length,
      scored: scores.length,
      failed: errors.length,
      duration_ms: durationMs,
      an_score_version: "0.2",
      runner: "score-dataset-v1",
    },
    scores: scores.map(s => ({
      service_slug: s.service_slug,
      score: s.score,
      execution_score: s.execution_score,
      access_readiness_score: s.access_readiness_score,
      aggregate_recommendation_score: s.aggregate_recommendation_score,
      confidence: s.confidence,
      tier: s.tier,
      tier_label: s.tier_label,
      probe_metadata: s.probe_metadata,
      calculated_at: s.calculated_at,
    })),
    errors,
  }, null, 2));
  console.log(`  📄 Results written to ${outputPath}\n`);

  return {
    total: dataset.length,
    scored: scores.length,
    failed: errors.length,
    scores,
    errors,
    persistence,
    duration_ms: durationMs,
  };
}

// ─── CLI Entry Point ───

const isDirectRun = process.argv[1]?.endsWith("score-dataset.ts") ||
  process.argv[1]?.endsWith("score-dataset.js");

if (isDirectRun) {
  const args = process.argv.slice(2);
  const dryRun = args.includes("--dry-run");
  const apiUrlArg = args.find(a => a.startsWith("--api-url="))?.split("=")[1] ??
    args[args.indexOf("--api-url") + 1];
  const apiUrl = apiUrlArg ?? process.env.RHUMB_API_URL ?? "http://localhost:8000";
  const persistToApi = args.includes("--persist");

  runDatasetScoring({ dryRun, apiUrl, persistToApi })
    .then(result => {
      if (result.failed > 0) process.exit(1);
    })
    .catch(err => {
      console.error("Fatal error:", err);
      process.exit(2);
    });
}

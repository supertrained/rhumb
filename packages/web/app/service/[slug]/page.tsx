import React from "react";
import Link from "next/link";
import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { getServiceScore } from "../../../lib/api";
import type { ServiceScoreViewModel } from "../../../lib/types";
import { ScoreDisplay, TierBadge } from "../../../components/ScoreDisplay";
import { AutonomySection } from "../../../components/autonomy-section";
import { getTierInfo, getTierInfoFromString } from "../../../lib/utils";

function scoreLabel(value: number | null): string {
  return value === null ? "—" : value.toFixed(1);
}

function freshnessLabel(score: ServiceScoreViewModel): string {
  if (score.evidenceFreshness) return score.evidenceFreshness;
  if (score.calculatedAt) return `Updated ${score.calculatedAt}`;
  return "Freshness pending";
}

function buildServiceJsonLd(score: ServiceScoreViewModel): Record<string, unknown> {
  const additionalProperty = [
    score.executionScore !== null
      ? { "@type": "PropertyValue", name: "execution_score", value: score.executionScore.toFixed(1) }
      : null,
    score.accessReadinessScore !== null
      ? { "@type": "PropertyValue", name: "access_readiness_score", value: score.accessReadinessScore.toFixed(1) }
      : null,
    score.tierLabel ?? score.tier
      ? { "@type": "PropertyValue", name: "tier", value: score.tierLabel ?? score.tier ?? "Pending" }
      : null,
    score.confidence !== null
      ? { "@type": "PropertyValue", name: "confidence", value: score.confidence.toFixed(2) }
      : null,
  ].filter((p): p is { "@type": "PropertyValue"; name: string; value: string } => p !== null);

  return {
    "@context": "https://schema.org",
    "@type": "SoftwareApplication",
    name: score.serviceSlug,
    url: `/service/${score.serviceSlug}`,
    description: score.explanation ?? "AN Score profile from Rhumb",
    ...(score.aggregateRecommendationScore !== null
      ? {
          aggregateRating: {
            "@type": "Rating",
            ratingValue: score.aggregateRecommendationScore.toFixed(1),
            bestRating: "10",
          },
        }
      : {}),
    ...(additionalProperty.length > 0 ? { additionalProperty } : {}),
  };
}

function renderJsonLd(payload: Record<string, unknown>): JSX.Element {
  return <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(payload) }} />;
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;

  return {
    title: `${slug} | Rhumb`,
    description: `Execution and access-readiness profile for ${slug} with live AN Score evidence.`,
    alternates: { canonical: `/service/${slug}` },
    openGraph: {
      title: `${slug} | Rhumb`,
      description: `AN Score profile for ${slug}: execution, access, and tier breakdown.`,
      images: [{ url: `/service/${slug}/og`, width: 1200, height: 630 }],
    },
  };
}

// Score dimension bar
function DimensionBar({
  label,
  value,
  description,
}: {
  label: string;
  value: number | null;
  description?: string;
}) {
  const tier = getTierInfo(value);
  const pct = value !== null ? Math.min((value / 10) * 100, 100) : 0;

  return (
    <div className="py-3 border-b border-slate-800 last:border-0">
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm text-slate-300 font-medium">{label}</span>
        <span className={`font-mono font-bold text-lg ${tier.textClass}`}>
          {scoreLabel(value)}
        </span>
      </div>
      <div className="h-1.5 bg-slate-800 rounded-full overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-700"
          style={{ width: `${pct}%`, backgroundColor: tier.hex }}
        />
      </div>
      {description && (
        <p className="mt-1.5 text-xs text-slate-500 leading-relaxed">{description}</p>
      )}
    </div>
  );
}

export default async function ServicePage({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<JSX.Element> {
  const { slug } = await params;
  const score = await getServiceScore(slug);

  if (score === null) {
    notFound();
  }

  const structuredData = buildServiceJsonLd(score);
  const tierInfo = getTierInfoFromString(score.tier ?? score.tierLabel);
  const displayName = score.serviceSlug
    .split("-")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");

  return (
    <div className="bg-navy min-h-screen">
      {renderJsonLd(structuredData)}

      {/* Service header */}
      <section className="relative border-b border-slate-800 overflow-hidden">
        <div className="absolute inset-0 bg-grid opacity-30 pointer-events-none" />
        <div className="absolute inset-0 pointer-events-none" style={{ background: `radial-gradient(ellipse at top left, ${tierInfo.hex}08 0%, transparent 60%)` }} />

        <div className="relative max-w-4xl mx-auto px-6 py-12">
          <Link
            href="/leaderboard"
            className="text-xs font-mono text-slate-500 hover:text-amber transition-colors inline-flex items-center gap-1 mb-6"
          >
            ← Leaderboard
          </Link>

          <div className="flex items-start gap-6 flex-wrap">
            {/* Score badge */}
            <ScoreDisplay
              score={score.aggregateRecommendationScore}
              size="large"
              showLabel
            />

            {/* Service info */}
            <div className="flex-1 min-w-0">
              <h1 className="font-display font-bold text-3xl sm:text-4xl text-slate-100 tracking-tight">
                {displayName}
              </h1>
              <div className="mt-3 flex flex-wrap items-center gap-3">
                <TierBadge tier={score.tier} label={score.tierLabel ?? undefined} />
                {score.confidence !== null && (
                  <span className="text-xs font-mono text-slate-500">
                    Confidence{" "}
                    <span className="text-slate-400">{score.confidence.toFixed(2)}</span>
                  </span>
                )}
                <span className="text-xs font-mono text-slate-600">{freshnessLabel(score)}</span>
              </div>

              {score.explanation && (
                <p className="mt-4 text-sm text-slate-400 leading-relaxed max-w-xl">
                  {score.explanation}
                </p>
              )}
            </div>
          </div>
        </div>
      </section>

      <div className="max-w-4xl mx-auto px-6 py-10 grid md:grid-cols-3 gap-6">
        {/* Left column: score breakdown */}
        <div className="md:col-span-2 space-y-6">
          {/* Score breakdown */}
          <section className="bg-surface border border-slate-800 rounded-xl p-6">
            <h2 className="font-display font-semibold text-slate-100 text-lg mb-4">Score breakdown</h2>
            <DimensionBar
              label="Execution Score"
              value={score.executionScore}
              description="Measures reliability, idempotency, error ergonomics, latency distribution, and schema stability."
            />
            <DimensionBar
              label="Access Readiness Score"
              value={score.accessReadinessScore}
              description="Measures how easily an agent can onboard, authenticate, and start using this service autonomously."
            />
            <DimensionBar
              label="Aggregate AN Score"
              value={score.aggregateRecommendationScore}
              description="Composite score: 70% execution + 30% access readiness."
            />
          </section>

          {/* Autonomy breakdown */}
          <AutonomySection
            p1Score={score.p1Score ?? null}
            g1Score={score.g1Score ?? null}
            w1Score={score.w1Score ?? null}
            p1Rationale={score.p1Rationale ?? null}
            g1Rationale={score.g1Rationale ?? null}
            w1Rationale={score.w1Rationale ?? null}
            autonomyTier={score.autonomyTier ?? null}
          />

          {/* Active failure modes */}
          <section className="bg-surface border border-slate-800 rounded-xl p-6">
            <h2 className="font-display font-semibold text-slate-100 text-lg mb-4">
              Active failure modes
            </h2>
            {score.activeFailures.length > 0 ? (
              <ul className="space-y-2">
                {score.activeFailures.map((failure) => (
                  <li
                    key={failure.id ?? failure.summary}
                    className="flex items-start gap-3 text-sm text-slate-400"
                  >
                    <span className="text-score-limited mt-0.5 shrink-0">▲</span>
                    {failure.summary}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-slate-500">No active failure modes reported.</p>
            )}
          </section>

          {/* Agent consumption */}
          <section className="bg-surface border border-slate-800 rounded-xl p-6">
            <h2 className="font-display font-semibold text-slate-100 text-lg mb-4">Use in your agent</h2>
            <div className="bg-navy border border-slate-800 rounded-lg overflow-hidden">
              <div className="flex items-center gap-2 px-4 py-2.5 border-b border-slate-800">
                <div className="w-2 h-2 rounded-full bg-slate-700" />
                <div className="w-2 h-2 rounded-full bg-slate-700" />
                <div className="w-2 h-2 rounded-full bg-slate-700" />
                <span className="ml-2 text-xs font-mono text-slate-600">cli</span>
              </div>
              <div className="p-4 font-mono text-sm text-slate-400">
                <div>
                  <span className="text-slate-600">$ </span>
                  <span className="text-amber">rhumb score {score.serviceSlug}</span>
                </div>
                {score.aggregateRecommendationScore !== null && (
                  <div className="mt-2 pl-4 space-y-0.5">
                    <div className={tierInfo.textClass}>
                      ● {displayName}{" "}
                      <span className="text-slate-100 font-bold">
                        {score.aggregateRecommendationScore.toFixed(1)}
                      </span>{" "}
                      {tierInfo.label}
                    </div>
                    {score.executionScore !== null && (
                      <div className="text-slate-600">
                        {"  "}exec: {score.executionScore.toFixed(1)} · access:{" "}
                        {score.accessReadinessScore?.toFixed(1) ?? "—"}
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          </section>
        </div>

        {/* Right column: alternatives + meta */}
        <div className="space-y-6">
          {/* Tier card */}
          <div
            className={`bg-surface border rounded-xl p-5 ${tierInfo.borderClass}`}
          >
            <p className="text-xs font-mono text-slate-500 mb-2">Overall tier</p>
            <div className={`font-display font-bold text-2xl ${tierInfo.textClass}`}>
              {tierInfo.label}
            </div>
            <div className={`mt-3 h-1 rounded-full ${tierInfo.bgClass}`}>
              <div
                className="h-full rounded-full"
                style={{
                  width: `${Math.min(((score.aggregateRecommendationScore ?? 0) / 10) * 100, 100)}%`,
                  backgroundColor: tierInfo.hex,
                }}
              />
            </div>
            <p className="mt-2 text-xs font-mono text-slate-600">
              {scoreLabel(score.aggregateRecommendationScore)} / 10.0
            </p>
          </div>

          {/* Alternatives */}
          <section className="bg-surface border border-slate-800 rounded-xl p-5">
            <h2 className="font-display font-semibold text-slate-100 text-base mb-4">Alternatives</h2>
            {score.alternatives.length > 0 ? (
              <ul className="space-y-2">
                {score.alternatives.map((alt) => {
                  const altTier = getTierInfo(alt.score);
                  return (
                    <li key={alt.serviceSlug}>
                      <Link
                        href={`/service/${alt.serviceSlug}`}
                        className="flex items-center justify-between group py-1"
                      >
                        <span className="text-sm text-slate-400 group-hover:text-amber transition-colors font-medium">
                          {alt.serviceSlug}
                        </span>
                        {alt.score !== null && (
                          <span className={`text-sm font-mono font-bold ${altTier.textClass}`}>
                            {alt.score.toFixed(1)}
                          </span>
                        )}
                      </Link>
                    </li>
                  );
                })}
              </ul>
            ) : (
              <p className="text-sm text-slate-500">No alternatives captured yet.</p>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}

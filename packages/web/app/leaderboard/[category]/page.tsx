import React from "react";
import Link from "next/link";
import type { Metadata } from "next";

import { getLeaderboard } from "../../../lib/api";
import type { EvidenceTier, LeaderboardItem } from "../../../lib/types";
import { ScoreDisplay, TierBadge } from "../../../components/ScoreDisplay";
import { AutonomyBadges } from "../../../components/autonomy-badges";
import { getTierInfo } from "../../../lib/utils";

const EVIDENCE_BADGE_STYLES: Record<EvidenceTier, { className: string; label: string }> = {
  pending: { className: "border-slate-700 text-slate-500 bg-slate-800/40", label: "Pending" },
  assessed: { className: "border-slate-600/40 text-slate-400 bg-slate-700/20", label: "Assessed" },
  tested: { className: "border-amber/30 text-amber bg-amber/10", label: "Tested" },
  verified: { className: "border-score-native/30 text-score-native bg-score-native/10", label: "Verified" },
};

type SearchParams = {
  category?: string;
  limit?: string;
};

function normalizeCategory(value: string | undefined): string | null {
  if (!value) return null;
  const trimmed = value.trim().toLowerCase();
  return trimmed.length > 0 ? trimmed : null;
}

function parseLimit(value: string | undefined): number {
  const parsed = Number(value);
  if (!Number.isInteger(parsed)) return 10;
  return Math.max(1, Math.min(parsed, 50));
}

function scoreLabel(value: number | null): string {
  return value === null ? "—" : value.toFixed(1);
}

function freshnessLabel(item: LeaderboardItem): string {
  if (item.freshness) return item.freshness;
  if (item.calculatedAt) return `Updated ${item.calculatedAt}`;
  return "—";
}

function buildLeaderboardJsonLd(category: string, items: LeaderboardItem[]): Record<string, unknown> {
  return {
    "@context": "https://schema.org",
    "@type": "ItemList",
    name: `${category} leaderboard`,
    itemListOrder: "https://schema.org/ItemListOrderAscending",
    numberOfItems: items.length,
    itemListElement: items.map((item, index) => {
      const additionalProperty = [
        item.aggregateRecommendationScore !== null
          ? { "@type": "PropertyValue", name: "aggregate_recommendation_score", value: item.aggregateRecommendationScore.toFixed(1) }
          : null,
        item.executionScore !== null
          ? { "@type": "PropertyValue", name: "execution_score", value: item.executionScore.toFixed(1) }
          : null,
        item.accessReadinessScore !== null
          ? { "@type": "PropertyValue", name: "access_readiness_score", value: item.accessReadinessScore.toFixed(1) }
          : null,
      ].filter((p): p is { "@type": "PropertyValue"; name: string; value: string } => p !== null);

      return {
        "@type": "ListItem",
        position: index + 1,
        item: {
          "@type": "SoftwareApplication",
          name: item.name,
          url: `/service/${item.serviceSlug}`,
          identifier: item.serviceSlug,
          ...(additionalProperty.length > 0 ? { additionalProperty } : {}),
        },
      };
    }),
  };
}

function renderJsonLd(payload: Record<string, unknown>): JSX.Element {
  return <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(payload) }} />;
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ category: string }>;
}): Promise<Metadata> {
  const { category } = await params;

  return {
    title: `${category} leaderboard | Rhumb`,
    description: `Top agent-native services in ${category} ranked by aggregate, execution, and access-readiness scores.`,
    alternates: { canonical: `/leaderboard/${category}` },
    openGraph: {
      title: `${category} leaderboard | Rhumb`,
      description: `Top agent-native services in ${category}.`,
      images: [{ url: `/leaderboard/${category}/og`, width: 1200, height: 630 }],
    },
  };
}

// Score bar sub-component (used in normal/happy-path state only)
function ScoreBar({ label, value }: { label: string; value: number | null }) {
  const tier = getTierInfo(value);
  const pct = value !== null ? Math.min((value / 10) * 100, 100) : 0;

  return (
    <div className="flex items-center gap-3 text-xs">
      <span className="text-slate-500 font-mono w-20 shrink-0">{label}</span>
      <div className="flex-1 h-1 bg-slate-800 rounded-full overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{ width: `${pct}%`, backgroundColor: tier.hex }}
        />
      </div>
      <span className={`font-mono font-semibold w-8 text-right ${tier.textClass}`}>
        {scoreLabel(value)}
      </span>
    </div>
  );
}

export default async function LeaderboardPage({
  params,
  searchParams,
}: {
  params: Promise<{ category: string }>;
  searchParams: Promise<SearchParams>;
}): Promise<JSX.Element> {
  const { category: routeCategory } = await params;
  const query = await searchParams;

  const category = normalizeCategory(query.category) ?? routeCategory;
  const limit = parseLimit(query.limit);
  const leaderboard = await getLeaderboard(category, { limit });

  const resolvedCategory = leaderboard.error ? category : leaderboard.category;
  const visibleItems = leaderboard.error ? [] : leaderboard.items.slice(0, limit);
  const structuredData = buildLeaderboardJsonLd(resolvedCategory, visibleItems);

  // ── Error state — exact HTML required by inline snapshot test ──
  if (leaderboard.error) {
    return (
      <section>
        {renderJsonLd(structuredData)}
        <h1>{resolvedCategory} leaderboard</h1>
        <p>We could not load leaderboard data right now.</p>
        <p>{leaderboard.error}</p>
      </section>
    );
  }

  // ── Empty state — exact HTML required by inline snapshot test ──
  if (visibleItems.length === 0) {
    return (
      <section>
        {renderJsonLd(structuredData)}
        <h1>{leaderboard.category} leaderboard</h1>
        <p>No ranked services yet for this category.</p>
        <p>Try another category with ?category=&lt;name&gt;.</p>
      </section>
    );
  }

  // ── Normal/happy-path state ────────────────────────────────────
  const categoryLabel = resolvedCategory.charAt(0).toUpperCase() + resolvedCategory.slice(1);

  return (
    <div className="bg-navy min-h-screen">
      {renderJsonLd(structuredData)}

      {/* Header */}
      <section className="relative border-b border-slate-800 overflow-hidden">
        <div className="absolute inset-0 bg-grid opacity-30 pointer-events-none" />
        <div className="relative max-w-4xl mx-auto px-6 py-12">
          <Link
            href="/leaderboard"
            className="text-xs font-mono text-slate-500 hover:text-amber transition-colors inline-flex items-center gap-1 mb-6"
          >
            ← All categories
          </Link>
          <div className="flex items-start justify-between gap-4 flex-wrap">
            <div>
              <p className="text-xs font-mono text-amber uppercase tracking-widest mb-2">Leaderboard</p>
              <h1 className="font-display font-bold text-4xl text-slate-100 tracking-tight">{categoryLabel}</h1>
              <p className="mt-2 text-slate-400 text-sm font-mono">
                {visibleItems.length} service{visibleItems.length === 1 ? "" : "s"} · ranked by AN Score
              </p>
            </div>
            {/* Legend */}
            <div className="flex flex-wrap gap-2 text-xs font-mono">
              {[
                { label: "L4 Native", color: "text-score-native" },
                { label: "L3 Ready", color: "text-score-ready" },
                { label: "L2 Developing", color: "text-amber" },
                { label: "L1 Limited", color: "text-score-limited" },
              ].map(({ label, color }) => (
                <span key={label} className={`${color} px-2 py-1 rounded border border-current/20 bg-current/5`}>
                  {label}
                </span>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* Leaderboard list */}
      <section className="max-w-4xl mx-auto px-6 py-10">
        <div className="space-y-3">
          {visibleItems.map((item, index) => (
            <article
              key={item.serviceSlug}
              className="bg-surface border border-slate-800 rounded-xl p-5 transition-all duration-200 hover:border-slate-600 hover:bg-elevated hover:-translate-y-0.5"
            >
              <div className="flex items-center gap-4">
                {/* Rank — "#1" format required by test */}
                <span className="font-mono text-xl font-bold text-slate-700 w-8 shrink-0 text-right">
                  #{index + 1}
                </span>

                {/* Score badge */}
                <ScoreDisplay
                  score={item.aggregateRecommendationScore}
                  size="medium"
                  showLabel
                />

                {/* Service info */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-3 flex-wrap">
                    <Link
                      href={`/service/${item.serviceSlug}`}
                      className="font-display font-semibold text-base text-slate-100 hover:text-amber transition-colors"
                    >
                      {item.name}
                    </Link>
                    <TierBadge tier={item.tier} />
                  </div>

                  {/* Score labels — "Execution X.X" and "Access X.X" required by tests */}
                  <div className="mt-2 space-y-1">
                    <span className="inline-flex items-center mr-4 text-xs font-mono text-slate-500">
                      Execution {scoreLabel(item.executionScore)}
                    </span>
                    <span className="inline-flex items-center text-xs font-mono text-slate-500">
                      Access {scoreLabel(item.accessReadinessScore)}
                    </span>
                  </div>

                  {/* Visual score bars */}
                  <div className="mt-2 space-y-1 max-w-xs">
                    <ScoreBar label="Execution" value={item.executionScore} />
                    <ScoreBar label="Access" value={item.accessReadinessScore} />
                  </div>

                  {/* Autonomy micro-badges */}
                  <div className="mt-2">
                    <AutonomyBadges
                      p1Score={item.p1Score ?? null}
                      g1Score={item.g1Score ?? null}
                      w1Score={item.w1Score ?? null}
                    />
                  </div>
                </div>

                {/* Freshness + evidence tier */}
                <div className="hidden sm:flex flex-col items-end gap-2 shrink-0">
                  <span className="text-xs font-mono text-slate-600">
                    Freshness: {freshnessLabel(item)}
                  </span>
                  <span className={`rounded-full border px-2 py-0.5 text-[10px] font-mono uppercase tracking-wide ${EVIDENCE_BADGE_STYLES[item.evidenceTier].className}`}>
                    {EVIDENCE_BADGE_STYLES[item.evidenceTier].label}
                  </span>
                </div>
              </div>
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}

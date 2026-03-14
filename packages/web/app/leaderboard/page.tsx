import React from "react";
import Link from "next/link";
import type { Metadata } from "next";

import { getCategories } from "../../lib/api";
import { CATEGORY_INFO, ORDERED_SLUGS } from "../../lib/categories";

// ---------- Metadata ----------

export const metadata: Metadata = {
  title: "Leaderboard | Rhumb",
  description:
    "Browse agent-native tool rankings across 11 categories: AI, payments, auth, and more.",
  alternates: { canonical: "/leaderboard" },
  openGraph: {
    title: "Leaderboard | Rhumb",
    description: "Agent-native tool rankings across 11 categories.",
    images: [{ url: "/api/og", width: 1200, height: 630 }],
  },
};

// Category icons as SVG path data
const CATEGORY_ICONS: Record<string, JSX.Element> = {
  payments: (
    <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
      <rect x="2" y="5" width="16" height="12" rx="2" stroke="currentColor" strokeWidth="1.5"/>
      <path d="M2 9H18" stroke="currentColor" strokeWidth="1.5"/>
      <rect x="4" y="11.5" width="4" height="2" rx="0.5" fill="currentColor"/>
    </svg>
  ),
  ai: (
    <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
      <circle cx="10" cy="10" r="3" stroke="currentColor" strokeWidth="1.5"/>
      <path d="M10 3V5M10 15V17M3 10H5M15 10H17M5.2 5.2L6.6 6.6M13.4 13.4L14.8 14.8M14.8 5.2L13.4 6.6M6.6 13.4L5.2 14.8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
    </svg>
  ),
  analytics: (
    <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
      <path d="M3 14L7 9L11 11L17 5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
      <path d="M3 17H17" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
    </svg>
  ),
  auth: (
    <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
      <rect x="5" y="9" width="10" height="8" rx="1.5" stroke="currentColor" strokeWidth="1.5"/>
      <path d="M7 9V7C7 5.3 8.3 4 10 4C11.7 4 13 5.3 13 7V9" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
      <circle cx="10" cy="13" r="1" fill="currentColor"/>
    </svg>
  ),
  calendar: (
    <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
      <rect x="3" y="4" width="14" height="13" rx="2" stroke="currentColor" strokeWidth="1.5"/>
      <path d="M3 8H17M7 3V5M13 3V5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
      <rect x="7" y="11" width="2" height="2" rx="0.5" fill="currentColor"/>
      <rect x="11" y="11" width="2" height="2" rx="0.5" fill="currentColor"/>
    </svg>
  ),
  crm: (
    <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
      <circle cx="10" cy="7" r="3" stroke="currentColor" strokeWidth="1.5"/>
      <path d="M4 17C4 14.2 6.7 12 10 12C13.3 12 16 14.2 16 17" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
    </svg>
  ),
  devops: (
    <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
      <path d="M10 3L14 10H6L10 3Z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round"/>
      <path d="M5 13C5 15.2 7.2 17 10 17C12.8 17 15 15.2 15 13" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
    </svg>
  ),
  email: (
    <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
      <rect x="2" y="5" width="16" height="12" rx="2" stroke="currentColor" strokeWidth="1.5"/>
      <path d="M2 7L10 12L18 7" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
    </svg>
  ),
  search: (
    <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
      <circle cx="9" cy="9" r="5" stroke="currentColor" strokeWidth="1.5"/>
      <path d="M13 13L17 17" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
    </svg>
  ),
  social: (
    <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
      <circle cx="5" cy="10" r="2.5" stroke="currentColor" strokeWidth="1.5"/>
      <circle cx="15" cy="5" r="2.5" stroke="currentColor" strokeWidth="1.5"/>
      <circle cx="15" cy="15" r="2.5" stroke="currentColor" strokeWidth="1.5"/>
      <path d="M7.3 9L12.7 6M7.3 11L12.7 14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
    </svg>
  ),
};

// ---------- Page ----------

export default async function LeaderboardHubPage(): Promise<JSX.Element> {
  const categoryData = await getCategories();
  const countMap: Record<string, number> = Object.fromEntries(
    categoryData.map((c) => [c.slug, c.serviceCount])
  );

  // Build a text summary for agent/SEO readability
  const categorySummaries = ORDERED_SLUGS
    .map((slug) => {
      const info = CATEGORY_INFO[slug];
      if (!info) return null;
      const count = countMap[slug] ?? 0;
      return `${info.name} (${count} service${count === 1 ? "" : "s"}): ${info.description}`;
    })
    .filter(Boolean);

  const totalServices = Object.values(countMap).reduce((a, b) => a + b, 0);

  return (
    <div className="bg-navy min-h-screen">
      {/* Header */}
      <section className="relative border-b border-slate-800 overflow-hidden">
        <div className="absolute inset-0 bg-grid opacity-30 pointer-events-none" />
        <div className="relative max-w-6xl mx-auto px-6 py-14">
          <p className="text-xs font-mono text-amber uppercase tracking-widest mb-3">Leaderboard</p>
          <h1 className="font-display font-bold text-4xl sm:text-5xl text-slate-100 tracking-tight">
            Agent-native rankings
          </h1>
          <p className="mt-3 text-slate-400 max-w-xl leading-relaxed">
            Rhumb scores {totalServices} developer APIs across {ORDERED_SLUGS.length} categories
            on execution reliability and access readiness for autonomous AI agents.
            Each service is rated on 20 dimensions using Rhumb&apos;s Agent-Native Score (AN&nbsp;Score).
          </p>
        </div>
      </section>

      {/* Machine-readable / agent-extractable summary */}
      <section className="max-w-6xl mx-auto px-6 pt-8">
        <div className="text-sm text-slate-500 leading-relaxed space-y-1">
          <p>
            Categories: {categorySummaries.join(". ")}.
          </p>
          <p>
            Scores range from 0.0 to 10.0. Tiers: L4 Native (8.0–10.0), L3 Ready (6.0–7.9),
            L2 Developing (4.0–5.9), L1 Limited (0.0–3.9). Formula: 70% Execution + 30% Access Readiness.
          </p>
        </div>
      </section>

      {/* Category grid */}
      <section className="max-w-6xl mx-auto px-6 py-12">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {ORDERED_SLUGS.map((slug, i) => {
            const info = CATEGORY_INFO[slug];
            if (!info) return null;
            const count = countMap[slug] ?? 0;
            const icon = CATEGORY_ICONS[slug];

            return (
              <Link
                key={slug}
                href={`/leaderboard/${slug}`}
                aria-label={`${info.name} leaderboard`}
                className="group block"
                style={{ animationDelay: `${i * 50}ms` }}
              >
                <article className="h-full bg-surface border border-slate-800 rounded-xl p-6 transition-all duration-200 hover:border-slate-600 hover:bg-elevated hover:-translate-y-0.5">
                  {/* Icon + count row */}
                  <div className="flex items-start justify-between mb-4">
                    <div className="w-10 h-10 rounded-lg bg-navy/60 border border-slate-800 flex items-center justify-center text-amber group-hover:border-amber/30 transition-colors">
                      {icon ?? (
                        <span className="text-xs font-mono font-bold text-amber">
                          {info.name.substring(0, 2).toUpperCase()}
                        </span>
                      )}
                    </div>
                    <span className="text-xs font-mono text-slate-600 px-2 py-0.5 rounded-full border border-slate-800 bg-navy/40">
                      {count > 0
                          ? `${count} service${count === 1 ? "" : "s"}`
                          : "Explore category"}
                    </span>
                  </div>

                  {/* Name */}
                  <h2 className="font-display font-semibold text-lg text-slate-100 group-hover:text-amber transition-colors mb-2">
                    {info.name}
                  </h2>

                  {/* Description */}
                  <p className="text-sm text-slate-400 leading-relaxed line-clamp-2">
                    {info.description}
                  </p>

                  {/* Arrow */}
                  <div className="mt-4 flex items-center justify-end text-slate-600 group-hover:text-amber transition-colors text-sm font-mono">
                    View rankings →
                  </div>
                </article>
              </Link>
            );
          })}
        </div>
      </section>
    </div>
  );
}

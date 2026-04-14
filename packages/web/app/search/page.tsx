import React, { Suspense } from "react";
import type { Metadata } from "next";
import Link from "next/link";

import { getServices } from "../../lib/api";
import { PUBLIC_TRUTH } from "../../lib/public-truth";
import { Search } from "../../components/Search";
import { ScoreDisplay } from "../../components/ScoreDisplay";

export const metadata: Metadata = {
  title: "Search | Rhumb",
  description: "Search agent-native developer tools and APIs scored by Rhumb.",
};

type Props = {
  searchParams: Promise<{ q?: string }>;
};

export default async function SearchPage({ searchParams }: Props): Promise<JSX.Element> {
  const { q } = await searchParams;
  const query = q?.trim() ?? "";
  const servicesLabel = PUBLIC_TRUTH.servicesLabel;

  const allServices = query ? await getServices() : [];
  const results = allServices.filter((s) => {
    const search = query.toLowerCase();
    return (
      s.name.toLowerCase().includes(search) ||
      s.slug.toLowerCase().includes(search) ||
      s.category.toLowerCase().includes(search) ||
      (s.description?.toLowerCase().includes(search) ?? false)
    );
  });

  return (
    <div className="bg-navy min-h-screen">
      {/* Header */}
      <section className="relative border-b border-slate-800 overflow-hidden">
        <div className="absolute inset-0 bg-grid opacity-30 pointer-events-none" />
        <div className="relative max-w-3xl mx-auto px-6 py-12">
          <p className="text-xs font-mono text-amber uppercase tracking-widest mb-4">Search</p>
          <h1 className="font-display font-bold text-3xl text-slate-100 tracking-tight mb-6">
            Find agent-native tools
          </h1>
          <Suspense>
            <Search />
          </Suspense>

          <div className="mt-8 rounded-2xl border border-amber/20 bg-surface/80 p-5 backdrop-blur-sm">
            <p className="text-xs font-mono text-amber uppercase tracking-widest">
              Before you wire a result into your flow
            </p>
            <p className="mt-3 text-sm text-slate-400 leading-relaxed">
              Sanity-check the trust posture, scoring methodology, and dispute path before you turn
              a search result into routing logic or vendor selection.
            </p>
            <div className="mt-4 flex flex-wrap gap-3 text-sm">
              <Link
                href="/trust"
                className="inline-flex rounded-lg border border-slate-700 px-4 py-2 text-slate-300 transition-colors duration-200 hover:border-slate-500 hover:text-slate-100"
              >
                Trust →
              </Link>
              <Link
                href="/methodology"
                className="inline-flex rounded-lg border border-slate-700 px-4 py-2 text-slate-300 transition-colors duration-200 hover:border-slate-500 hover:text-slate-100"
              >
                Methodology →
              </Link>
              <Link
                href="/providers#dispute-a-score"
                className="inline-flex rounded-lg border border-slate-700 px-4 py-2 text-slate-300 transition-colors duration-200 hover:border-slate-500 hover:text-slate-100"
              >
                Dispute a score →
              </Link>
            </div>
          </div>
        </div>
      </section>

      {/* Results */}
      <section className="max-w-3xl mx-auto px-6 py-10">
        {query ? (
          <>
            <p className="text-xs font-mono text-slate-500 mb-6">
              {results.length > 0
                ? `${results.length} result${results.length === 1 ? "" : "s"} for "${query}"`
                : `No results for "${query}"`}
            </p>

            {results.length > 0 ? (
              <div className="space-y-3">
                {results.map((service) => (
                  <Link key={service.slug} href={`/service/${service.slug}`} className="block group">
                    <article className="bg-surface border border-slate-800 rounded-xl p-5 flex items-center gap-4 transition-all duration-200 hover:border-slate-600 hover:bg-elevated">
                      <ScoreDisplay score={null} size="small" showLabel={false} />

                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="font-display font-semibold text-slate-100 group-hover:text-amber transition-colors">
                            {service.name}
                          </span>
                          <span className="text-xs text-slate-600 px-2 py-0.5 rounded-full border border-slate-800 bg-navy/40 font-mono">
                            {service.category}
                          </span>
                        </div>
                        {service.description && (
                          <p className="mt-1 text-sm text-slate-500 leading-relaxed line-clamp-1">
                            {service.description}
                          </p>
                        )}
                      </div>

                      <span className="text-slate-600 group-hover:text-amber transition-colors text-sm shrink-0">→</span>
                    </article>
                  </Link>
                ))}
              </div>
            ) : (
              <div className="bg-surface border border-slate-800 rounded-xl p-12 text-center">
                <p className="text-slate-500 text-sm mb-4">No services match your search.</p>
                <Link
                  href="/leaderboard"
                  className="text-sm text-amber hover:underline font-mono"
                >
                  Browse the full leaderboard →
                </Link>
              </div>
            )}
          </>
        ) : (
          <div className="text-center py-16">
            <p className="text-slate-500 text-sm font-mono mb-6">
              Search across {servicesLabel} scored APIs and developer tools.
            </p>
            <div className="flex flex-wrap justify-center gap-2">
              {["payments", "ai", "auth", "email", "devops", "search"].map((cat) => (
                <Link
                  key={cat}
                  href={`/leaderboard/${cat}`}
                  className="px-3 py-1.5 rounded-full border border-slate-800 text-xs font-mono text-slate-500 hover:border-amber/40 hover:text-amber transition-colors bg-surface"
                >
                  {cat}
                </Link>
              ))}
            </div>
          </div>
        )}
      </section>
    </div>
  );
}

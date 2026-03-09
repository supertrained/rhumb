import React from "react";
import Link from "next/link";
import type { Metadata } from "next";

import { getLeaderboard } from "../lib/api";
import type { LeaderboardItem } from "../lib/types";
import { ScoreDisplay, TierBadge } from "../components/ScoreDisplay";

export const metadata: Metadata = {
  title: "Rhumb | Agent-native tool discovery",
  description:
    "Discover top agent-native services with execution and access-readiness evidence. Every API scored for AI agents.",
};

function scoreLabel(value: number | null): string {
  return value === null ? "Pending" : value.toFixed(1);
}

function freshnessLabel(item: LeaderboardItem): string {
  if (item.freshness) return item.freshness;
  if (item.calculatedAt) return `Updated ${item.calculatedAt}`;
  return "Freshness pending";
}

const STATS = [
  { value: "50+", label: "services scored" },
  { value: "10", label: "categories" },
  { value: "17", label: "scored dimensions" },
  { value: "live", label: "probe data" },
];

export default async function HomePage(): Promise<JSX.Element> {
  const leaderboard = await getLeaderboard("payments", { limit: 3 });
  const previewItems = leaderboard.items.slice(0, 3);

  return (
    <div className="bg-navy min-h-screen">
      {/* ── Hero ─────────────────────────────────────────────── */}
      <section className="relative overflow-hidden">
        {/* Grid background */}
        <div className="absolute inset-0 bg-grid opacity-50 pointer-events-none" />

        {/* Amber radial glow */}
        <div
          className="absolute top-0 left-1/2 -translate-x-1/2 w-[600px] h-[400px] rounded-full pointer-events-none"
          style={{ background: "radial-gradient(ellipse at top, rgba(245,158,11,0.08) 0%, transparent 70%)" }}
        />

        <div className="relative max-w-6xl mx-auto px-6 pt-20 pb-16">
          {/* Eyebrow */}
          <div className="animate-fade-up flex items-center gap-2 mb-6">
            <span className="w-1.5 h-1.5 rounded-full bg-amber" />
            <span className="text-xs font-mono text-slate-400 uppercase tracking-widest">
              Agent-Native Score v0.2
            </span>
          </div>

          {/* Headline — exact text required by tests */}
          <h1 className="animate-fade-up animate-delay-100 font-display font-bold text-5xl sm:text-6xl lg:text-7xl text-slate-100 leading-[1.05] tracking-tight max-w-3xl">
            Find agent-native services in seconds
          </h1>

          <p className="animate-fade-up animate-delay-200 mt-6 text-lg text-slate-400 max-w-xl leading-relaxed">
            Rhumb maps execution reliability and access readiness so your agents
            pick the right primitive before they fail in production.
          </p>

          {/* Search bar */}
          <form
            action="/search"
            method="get"
            className="animate-fade-up animate-delay-300 mt-8 flex flex-col sm:flex-row gap-3 max-w-xl"
          >
            <div className="relative flex-1">
              <div className="absolute inset-y-0 left-4 flex items-center pointer-events-none text-slate-500">
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                  <path
                    d="M11 6.5C11 9.0 9.0 11 6.5 11C4.0 11 2 9.0 2 6.5C2 4.0 4.0 2 6.5 2C9.0 2 11 4.0 11 6.5ZM10.2 10.9L14 14.7"
                    stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"
                  />
                </svg>
              </div>
              <input
                aria-label="Search services"
                name="q"
                type="search"
                placeholder="Search services (e.g. payments API)"
                className="w-full pl-11 pr-4 py-3.5 rounded-xl bg-surface border border-slate-700 text-slate-100 placeholder-slate-500 text-sm outline-none focus:border-amber focus:ring-2 focus:ring-amber/20 transition-all duration-200"
              />
            </div>
            <button
              type="submit"
              className="px-6 py-3.5 rounded-xl bg-amber text-navy font-display font-semibold text-sm hover:bg-amber-dark transition-colors duration-200 shrink-0"
            >
              Search
            </button>
          </form>

          {/* CTAs */}
          <div className="animate-fade-up animate-delay-400 mt-5 flex flex-wrap gap-3">
            <Link
              href="/leaderboard"
              className="px-5 py-2.5 rounded-lg border border-slate-700 text-sm text-slate-300 hover:border-slate-500 hover:text-slate-100 transition-colors duration-200 font-medium"
            >
              Explore Leaderboard →
            </Link>
            <a
              href="#install"
              className="px-5 py-2.5 rounded-lg border border-slate-800 text-sm text-slate-500 hover:border-slate-700 hover:text-slate-400 transition-colors duration-200 font-mono"
            >
              $ rhumb install
            </a>
          </div>
        </div>
      </section>

      {/* ── Stats bar ────────────────────────────────────────── */}
      <section className="border-y border-slate-800 bg-surface/50">
        <div className="max-w-6xl mx-auto px-6 py-5">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            {STATS.map(({ value, label }, i) => (
              <div
                key={label}
                className="animate-fade-up text-center"
                style={{ animationDelay: `${(i + 5) * 100}ms` }}
              >
                <div className="font-mono font-bold text-2xl text-amber">{value}</div>
                <div className="text-xs text-slate-500 mt-0.5 font-mono uppercase tracking-wide">{label}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Featured leaderboard (Payments) ─────────────────── */}
      <section className="max-w-6xl mx-auto px-6 py-16">
        <div className="flex items-center justify-between mb-8">
          <div>
            <p className="text-xs font-mono text-amber uppercase tracking-widest mb-2">Featured · Payments</p>
            <h2 className="font-display font-bold text-2xl text-slate-100">Top services in payments</h2>
          </div>
          <Link
            href="/leaderboard/payments"
            className="hidden sm:inline-flex items-center gap-1.5 text-sm text-slate-400 hover:text-amber transition-colors font-mono"
          >
            Open full payments leaderboard
          </Link>
        </div>

        {leaderboard.error ? (
          <div className="bg-surface border border-slate-800 rounded-xl p-8 text-center">
            <p className="text-slate-400 text-sm">
              Live leaderboard preview is temporarily unavailable. You can still browse the
              {" "}
              <Link href="/leaderboard/payments" className="text-amber hover:underline">
                full leaderboard
              </Link>
              .
            </p>
          </div>
        ) : previewItems.length === 0 ? (
          <div className="bg-surface border border-slate-800 rounded-xl p-8 text-center">
            <p className="text-slate-500 text-sm">No ranked services published yet.</p>
          </div>
        ) : (
          <ol className="space-y-3" style={{ listStyle: "none", padding: 0 }}>
            {previewItems.map((item, index) => (
              <li key={item.serviceSlug}>
                <article className="bg-surface border border-slate-800 rounded-xl p-5 flex items-center gap-5 transition-all duration-200 hover:border-slate-600 hover:bg-elevated group">
                  {/* Rank */}
                  <span className="font-mono text-2xl font-bold text-slate-700 w-8 shrink-0 text-right">
                    {index + 1}
                  </span>

                  {/* Score badge */}
                  <ScoreDisplay
                    score={item.aggregateRecommendationScore}
                    size="medium"
                    showLabel
                  />

                  {/* Details */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-3 flex-wrap">
                      {/* Service name as anchor — test expects "Stripe</a>" */}
                      <Link
                        href={`/service/${item.serviceSlug}`}
                        className="font-display font-semibold text-slate-100 hover:text-amber transition-colors"
                      >
                        {item.name}
                      </Link>
                      <TierBadge tier={item.tier} />
                    </div>
                    <div className="mt-1.5 flex items-center gap-4 flex-wrap text-xs font-mono text-slate-500">
                      {/* "Aggregate X.X" text required by test */}
                      <span>Aggregate {scoreLabel(item.aggregateRecommendationScore)}</span>
                      <span>· Freshness {freshnessLabel(item)}</span>
                    </div>
                  </div>
                </article>
              </li>
            ))}
          </ol>
        )}

        {/* The test checks for "Open full payments leaderboard" — shown on mobile too */}
        <p className="mt-6">
          <Link
            href="/leaderboard/payments"
            className="text-sm text-slate-400 hover:text-amber transition-colors font-mono sm:hidden"
          >
            Open full payments leaderboard
          </Link>
        </p>
      </section>

      {/* ── Install CLI ───────────────────────────────────────── */}
      <section id="install" className="border-t border-slate-800 bg-surface/30">
        <div className="max-w-6xl mx-auto px-6 py-16 grid md:grid-cols-2 gap-12 items-center">
          <div>
            <p className="text-xs font-mono text-amber uppercase tracking-widest mb-3">CLI</p>
            <h2 className="font-display font-bold text-2xl text-slate-100 mb-4">
              Query Rhumb from your agents
            </h2>
            <p className="text-slate-400 text-sm leading-relaxed">
              Use the Rhumb CLI to fetch AN Scores programmatically. Perfect for
              agent routing logic, tool-selection prompts, and automated dependency
              evaluation.
            </p>
            <Link
              href="/leaderboard"
              className="mt-6 inline-flex px-5 py-2.5 rounded-lg bg-amber text-navy font-semibold text-sm hover:bg-amber-dark transition-colors duration-200"
            >
              Explore all categories →
            </Link>
          </div>

          <div className="bg-navy border border-slate-800 rounded-xl overflow-hidden">
            <div className="flex items-center gap-2 px-4 py-3 border-b border-slate-800">
              <div className="w-2.5 h-2.5 rounded-full bg-slate-700" />
              <div className="w-2.5 h-2.5 rounded-full bg-slate-700" />
              <div className="w-2.5 h-2.5 rounded-full bg-slate-700" />
              <span className="ml-2 text-xs font-mono text-slate-600">terminal</span>
            </div>
            <div className="p-5 font-mono text-sm space-y-2">
              <div>
                <span className="text-slate-600">$ </span>
                <span className="text-amber">rhumb score stripe</span>
              </div>
              <div className="text-slate-400 pl-4 space-y-0.5">
                <div>
                  <span className="text-score-native">●</span>
                  {" "}Stripe{" "}
                  <span className="text-slate-100 font-bold">8.3</span>
                  {" "}
                  <span className="text-score-native">L4 Native</span>
                </div>
                <div className="text-slate-600">  exec: 9.0 · access: 6.6</div>
                <div className="text-slate-600">  updated: 2 hours ago</div>
              </div>
              <div className="pt-1">
                <span className="text-slate-600">$ </span>
                <span className="text-amber">rhumb leaderboard payments --limit 3</span>
              </div>
              <div className="text-slate-400 pl-4">
                <div><span className="text-slate-600">1.</span> stripe <span className="text-score-native">8.3</span></div>
                <div><span className="text-slate-600">2.</span> lemon-squeezy <span className="text-score-ready">7.0</span></div>
                <div><span className="text-slate-600">3.</span> square <span className="text-score-ready">6.7</span></div>
              </div>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}

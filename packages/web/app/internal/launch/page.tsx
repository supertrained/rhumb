import React from "react";
import Link from "next/link";
import { notFound } from "next/navigation";

import { getLaunchDashboard } from "../../../lib/api";

function formatPct(value: number | null): string {
  if (value === null) {
    return "—";
  }
  return `${(value * 100).toFixed(1)}%`;
}

function formatTimestamp(value: string | null): string {
  if (!value) {
    return "No activity yet";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return date.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export default async function InternalLaunchDashboardPage({
  searchParams,
}: {
  searchParams: Promise<{ key?: string; window?: "24h" | "7d" | "launch" }>;
}): Promise<JSX.Element> {
  const { key, window = "7d" } = await searchParams;

  const adminKey = process.env.RHUMB_ADMIN_SECRET ?? "";
  const configuredDashboardKey = process.env.RHUMB_LAUNCH_DASHBOARD_KEY ?? "";
  const dashboardKey = configuredDashboardKey || adminKey;
  const dashboardAuthMode = configuredDashboardKey ? "dashboard" : "admin";
  if (!dashboardKey || key !== dashboardKey) {
    notFound();
  }

  const dashboard = await getLaunchDashboard(window, dashboardKey, dashboardAuthMode);
  if (dashboard === null) {
    notFound();
  }

  const windowLinks: Array<{ value: "24h" | "7d" | "launch"; label: string }> = [
    { value: "24h", label: "24h" },
    { value: "7d", label: "7d" },
    { value: "launch", label: "Launch" },
  ];

  return (
    <div className="bg-navy min-h-screen">
      <div className="max-w-6xl mx-auto px-6 py-10">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <p className="text-xs font-mono uppercase tracking-[0.28em] text-amber">Internal</p>
            <h1 className="mt-3 font-display text-3xl text-slate-100 font-bold tracking-tight">
              Launch dashboard
            </h1>
            <p className="mt-2 text-sm text-slate-500">
              Internal telemetry for machine usage and outbound launch conversions.
            </p>
          </div>
          <div className="flex gap-2">
            {windowLinks.map((item) => (
              <Link
                key={item.value}
                href={`/internal/launch?key=${encodeURIComponent(key)}&window=${item.value}`}
                className={`rounded-full border px-3 py-1.5 text-xs font-mono transition-colors ${
                  dashboard.window === item.value
                    ? "border-amber/40 bg-amber/10 text-amber"
                    : "border-slate-800 text-slate-400 hover:border-slate-700"
                }`}
              >
                {item.label}
              </Link>
            ))}
          </div>
        </div>

        <div className="mt-8 grid gap-4 md:grid-cols-4">
          <section className="rounded-xl border border-slate-800 bg-surface p-5">
            <p className="text-xs font-mono text-slate-500">Queries</p>
            <p className="mt-2 text-3xl font-display font-bold text-slate-100">{dashboard.queries.total}</p>
            <p className="mt-2 text-xs text-slate-500">
              Machine-facing: {dashboard.queries.machineTotal}
            </p>
          </section>
          <section className="rounded-xl border border-slate-800 bg-surface p-5">
            <p className="text-xs font-mono text-slate-500">Known clients</p>
            <p className="mt-2 text-3xl font-display font-bold text-slate-100">{dashboard.queries.uniqueClients}</p>
            <p className="mt-2 text-xs text-slate-500">
              Repeat rate: {formatPct(dashboard.queries.repeatClientRate)}
            </p>
          </section>
          <section className="rounded-xl border border-slate-800 bg-surface p-5">
            <p className="text-xs font-mono text-slate-500">Outbound clicks</p>
            <p className="mt-2 text-3xl font-display font-bold text-slate-100">{dashboard.clicks.providerClicks}</p>
            <p className="mt-2 text-xs text-slate-500">
              Total tracked clicks: {dashboard.clicks.total}
            </p>
          </section>
          <section className="rounded-xl border border-slate-800 bg-surface p-5">
            <p className="text-xs font-mono text-slate-500">Coverage</p>
            <p className="mt-2 text-3xl font-display font-bold text-slate-100">{dashboard.coverage.publicServiceCount}</p>
            <p className="mt-2 text-xs text-slate-500">
              Window starts {formatTimestamp(dashboard.startAt)}
            </p>
          </section>
        </div>

        <div className="mt-6 grid gap-6 lg:grid-cols-2">
          <section className="rounded-xl border border-slate-800 bg-surface p-6">
            <h2 className="font-display text-lg text-slate-100 font-semibold">Query mix</h2>
            <p className="mt-1 text-sm text-slate-500">
              Latest activity {formatTimestamp(dashboard.queries.latestActivityAt)}
            </p>
            <div className="mt-5 grid gap-5 sm:grid-cols-2">
              <div>
                <p className="text-xs font-mono text-slate-500">By source</p>
                <ul className="mt-3 space-y-2 text-sm">
                  {dashboard.queries.bySource.map((row) => (
                    <li key={row.key} className="flex items-center justify-between text-slate-300">
                      <span>{row.key}</span>
                      <span className="font-mono text-slate-500">{row.count}</span>
                    </li>
                  ))}
                </ul>
              </div>
              <div>
                <p className="text-xs font-mono text-slate-500">Top query types</p>
                <ul className="mt-3 space-y-2 text-sm">
                  {dashboard.queries.topQueryTypes.map((row) => (
                    <li key={row.key} className="flex items-center justify-between text-slate-300">
                      <span>{row.key}</span>
                      <span className="font-mono text-slate-500">{row.count}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </section>

          <section className="rounded-xl border border-slate-800 bg-surface p-6">
            <h2 className="font-display text-lg text-slate-100 font-semibold">Outbound conversions</h2>
            <p className="mt-1 text-sm text-slate-500">
              Latest activity {formatTimestamp(dashboard.clicks.latestActivityAt)}
            </p>
            <div className="mt-5 grid gap-5 sm:grid-cols-2">
              <div>
                <p className="text-xs font-mono text-slate-500">Top provider domains</p>
                <ul className="mt-3 space-y-2 text-sm">
                  {dashboard.clicks.topProviderDomains.map((row) => (
                    <li key={row.key} className="flex items-center justify-between text-slate-300">
                      <span>{row.key}</span>
                      <span className="font-mono text-slate-500">{row.count}</span>
                    </li>
                  ))}
                </ul>
              </div>
              <div>
                <p className="text-xs font-mono text-slate-500">Dispute / contact clicks</p>
                <ul className="mt-3 space-y-2 text-sm text-slate-300">
                  <li className="flex items-center justify-between">
                    <span>Email disputes</span>
                    <span className="font-mono text-slate-500">{dashboard.clicks.disputeClicks.email}</span>
                  </li>
                  <li className="flex items-center justify-between">
                    <span>GitHub disputes</span>
                    <span className="font-mono text-slate-500">{dashboard.clicks.disputeClicks.github}</span>
                  </li>
                  <li className="flex items-center justify-between">
                    <span>Provider contact</span>
                    <span className="font-mono text-slate-500">{dashboard.clicks.disputeClicks.contact}</span>
                  </li>
                </ul>
              </div>
            </div>
          </section>
        </div>

        <div className="mt-6 grid gap-6 lg:grid-cols-2">
          <section className="rounded-xl border border-slate-800 bg-surface p-6">
            <h2 className="font-display text-lg text-slate-100 font-semibold">Top services</h2>
            <ul className="mt-4 space-y-2 text-sm">
              {dashboard.queries.topServices.map((row) => (
                <li key={row.key} className="flex items-center justify-between text-slate-300">
                  <span>{row.key}</span>
                  <span className="font-mono text-slate-500">{row.count}</span>
                </li>
              ))}
            </ul>
            <h3 className="mt-6 text-xs font-mono text-slate-500">Top searches</h3>
            <ul className="mt-3 space-y-2 text-sm">
              {dashboard.queries.topSearches.map((row) => (
                <li key={row.key} className="flex items-center justify-between text-slate-300">
                  <span>{row.key}</span>
                  <span className="font-mono text-slate-500">{row.count}</span>
                </li>
              ))}
            </ul>
          </section>

          <section className="rounded-xl border border-slate-800 bg-surface p-6">
            <h2 className="font-display text-lg text-slate-100 font-semibold">Provider CTR</h2>
            <div className="mt-4 space-y-3">
              {dashboard.clicks.providerCtr.map((row) => (
                <div
                  key={row.service_slug}
                  className="rounded-lg border border-slate-800 bg-navy px-4 py-3 text-sm"
                >
                  <div className="flex items-center justify-between">
                    <span className="text-slate-200">{row.service_slug}</span>
                    <span className="font-mono text-slate-500">{formatPct(row.ctr)}</span>
                  </div>
                  <p className="mt-1 text-xs text-slate-500">
                    {row.clicks} provider clicks / {row.views} service views
                  </p>
                </div>
              ))}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}

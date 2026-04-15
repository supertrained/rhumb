import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Pricing & How to Pay",
  description:
    "Pay for what you use. Choose governed API key, wallet-prefund, or x402 per-call rails, with BYOK or Agent Vault when provider control is the point, and inspect the active execution rail before you run it.",
  alternates: { canonical: "/pricing" },
  openGraph: {
    title: "Pricing & How to Pay — Rhumb",
    description:
      "Transparent usage-based pricing with governed API key, wallet-prefund, and x402 per-call rails, plus BYOK and Agent Vault provider-control modes.",
    type: "website",
    url: "https://rhumb.dev/pricing",
    siteName: "Rhumb",
  },
};

const rails = [
  {
    badge: "Default",
    badgeClass: "text-amber bg-amber/10 border-amber/20",
    title: "Governed API key",
    authHeader: "X-Rhumb-Key",
    moneyFlow: "Rhumb-managed account billing and controls.",
    useWhen: "Default production path for teams that want the lowest-heroics repeat workflow.",
    tradeoff: "Requires account signup before the first paid call.",
  },
  {
    badge: "Wallet-first",
    badgeClass: "text-emerald-300 bg-emerald-500/10 border-emerald-500/20",
    title: "Wallet-prefund",
    authHeader: "X-Rhumb-Key",
    moneyFlow: "Top up reusable balance from a wallet, then spend from that balance.",
    useWhen: "Best when wallet identity matters, but repeat throughput matters more than zero-signup purity.",
    tradeoff: "Adds a funding step before the steady-state execute path.",
  },
  {
    badge: "Zero signup",
    badgeClass: "text-amber bg-amber/10 border-amber/20",
    title: "x402 per-call",
    authHeader: "X-Payment",
    moneyFlow: "USDC on Base, authorized per request.",
    useWhen: "Best for one-off calls, demos, and request-level payment authorization.",
    tradeoff: "Not the easiest repeat-traffic rail today, and tx-hash proof shape still matters.",
  },
  {
    badge: "Provider control",
    badgeClass: "text-slate-300 bg-slate-800 border-slate-700",
    title: "BYOK or Agent Vault",
    authHeader: "Provider credential via Rhumb",
    moneyFlow:
      "You pay the provider directly; Rhumb routes with your provider-controlled credential instead of Rhumb-managed billing.",
    useWhen:
      "Best when you must keep vendor contracts under your control or inject an encrypted provider credential at execution time.",
    tradeoff:
      "You keep the provider-credential management burden, either directly or through Agent Vault setup.",
  },
] as const;

const agentPaths = [
  {
    title: "Governed API key",
    summary: "Create an account, estimate first, then execute with one stable header.",
    steps: [
      "Get X-Rhumb-Key from your org.",
      "Call estimate_capability or GET /v1/capabilities/{id}/execute/estimate before paid execution.",
      "Execute repeat traffic with X-Rhumb-Key.",
    ],
  },
  {
    title: "Wallet-prefund",
    summary: "Fund reusable balance from a wallet, then execute on the same X-Rhumb-Key rail as the default path.",
    steps: [
      "Use the wallet funding flow once.",
      "Top up reusable balance instead of paying every request individually.",
      "Keep steady-state execution on X-Rhumb-Key.",
    ],
  },
  {
    title: "x402 per-call",
    summary: "Use payment-as-authorization when zero-signup or per-request payment proof is the point.",
    steps: [
      "Call execute and read the HTTP 402 payment requirement.",
      "Send the exact asset and amount to the exact address on the exact network in the response.",
      "Retry with X-Payment from the same wallet.",
      "If your buyer emits wrapped proofs instead of the supported tx-hash flow, switch to wallet-prefund.",
    ],
  },
  {
    title: "BYOK or Agent Vault",
    summary:
      "Resolve the capability on the byok or agent_vault mode, then execute with your provider-controlled credential instead of Rhumb-managed billing.",
    steps: [
      "Use resolve_capability with credential_mode=byok when you want Rhumb to reference your provider key, or credential_mode=agent_vault when you want Rhumb to inject an encrypted provider credential at execution time.",
      "If the preferred provider is not ready yet, follow machine-readable recovery fields like recovery_hint.resolve_url, recovery_hint.credential_modes_url, recovery_hint.alternate_execute_hint, or recovery_hint.setup_handoff.",
      "Execute through Rhumb with your provider-controlled credential path.",
    ],
  },
] as const;

export default function PricingPage() {
  return (
    <div className="bg-navy min-h-screen">
      <div className="max-w-5xl mx-auto px-6 pt-14 pb-24">
        <header className="mb-16 max-w-3xl">
          <div className="flex items-center gap-3 mb-4">
            <span className="text-xs font-mono font-semibold text-amber uppercase tracking-widest">
              Pricing
            </span>
          </div>
          <h1 className="font-display font-bold text-3xl sm:text-4xl text-slate-100 leading-tight tracking-tight mb-6">
            Pay for what you use.
            <span className="block text-slate-400 mt-2">
              Pick the rail that matches your authorization model.
            </span>
          </h1>
          <p className="text-lg text-slate-400 leading-relaxed">
            Discovery, scoring, and browsing are always free. When your agent
            runs a capability through Rhumb, you pay upstream cost plus a
            transparent 20% markup, and you can inspect the active execution
            rail, health, and exact cost before you commit. No subscriptions,
            no seat fees, no minimums.
          </p>

          <div className="mt-8 rounded-2xl border border-amber/20 bg-surface/80 p-5 backdrop-blur-sm">
            <p className="text-xs font-mono text-amber uppercase tracking-widest">
              Before you choose a payment rail
            </p>
            <p className="mt-3 text-sm text-slate-400 leading-relaxed">
              Check the trust posture, scoring methodology, and provider dispute path first so
              your payment choice stays anchored to what Rhumb actually proves and how providers
              can challenge stale score assumptions.
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
        </header>

        <section className="mb-16">
          <h2 className="font-display font-bold text-2xl text-slate-100 mb-6 tracking-tight">
            Pricing model
          </h2>

          <div className="bg-surface border border-slate-800 rounded-xl p-6 mb-6">
            <div className="grid gap-6 sm:grid-cols-2">
              <div>
                <h3 className="font-display font-semibold text-lg text-slate-100 mb-3">
                  What stays true
                </h3>
                <ul className="space-y-2.5 text-sm text-slate-400">
                  <li className="flex items-start gap-2.5">
                    <span className="text-amber mt-0.5 text-xs">✓</span>
                    <span>
                      Rhumb charges <strong className="text-slate-200">upstream cost + 20%</strong>
                    </span>
                  </li>
                  <li className="flex items-start gap-2.5">
                    <span className="text-amber mt-0.5 text-xs">✓</span>
                    <span>Discovery, scoring, and browsing are always free</span>
                  </li>
                  <li className="flex items-start gap-2.5">
                    <span className="text-amber mt-0.5 text-xs">✓</span>
                    <span>Failed provider calls are not charged</span>
                  </li>
                  <li className="flex items-start gap-2.5">
                    <span className="text-amber mt-0.5 text-xs">✓</span>
                    <span>No subscriptions, no seat fees, no minimums</span>
                  </li>
                </ul>
              </div>

              <div className="bg-elevated border border-slate-700 rounded-lg p-5">
                <span className="text-[10px] font-mono text-slate-500 uppercase tracking-wider">
                  Example
                </span>
                <div className="mt-3 space-y-2 font-mono text-sm">
                  <div className="flex justify-between">
                    <span className="text-slate-400">Upstream cost</span>
                    <span className="text-slate-200">$0.0010</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">Rhumb markup (20%)</span>
                    <span className="text-slate-200">$0.0002</span>
                  </div>
                  <div className="border-t border-slate-700 pt-2 flex justify-between">
                    <span className="text-amber font-semibold">You pay</span>
                    <span className="text-amber font-semibold">$0.0012</span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div className="bg-elevated border border-amber/20 rounded-xl p-5">
            <div className="flex items-start gap-3">
              <span className="text-amber text-lg">💡</span>
              <div className="text-slate-400 text-sm leading-relaxed">
                <strong className="text-slate-200">Check the active rail before execution.</strong>{" "}
                Use the <code className="font-mono text-xs bg-surface px-1.5 py-0.5 rounded text-amber">estimate_capability</code>{" "}
                MCP tool or the REST API to see the active execution rail,
                health, and exact cost before you run it. Anonymous direct
                system-of-record paths also preserve machine-readable <code className="font-mono text-xs bg-surface px-1.5 py-0.5 rounded text-amber">execute_readiness</code>{" "}
                handoffs.
              </div>
            </div>
          </div>
        </section>

        <section className="mb-16">
          <h2 className="font-display font-bold text-2xl text-slate-100 mb-4 tracking-tight">
            Choose your rail
          </h2>
          <p className="text-slate-400 leading-relaxed mb-8 max-w-3xl">
            Same capability directory, different authorization and payment
            models. Most buyers should start with the governed API-key path,
            widen into wallet-prefund or x402 only when those payment
            properties matter, and use BYOK or Agent Vault when provider
            control is the real requirement.
          </p>

          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            {rails.map((rail) => (
              <article
                key={rail.title}
                className="bg-surface border border-slate-800 rounded-xl p-5"
              >
                <div className="flex items-center justify-between gap-3 mb-3">
                  <h3 className="font-display font-semibold text-lg text-slate-100">
                    {rail.title}
                  </h3>
                  <span
                    className={`border px-2 py-0.5 rounded font-mono text-[10px] uppercase tracking-widest ${rail.badgeClass}`}
                  >
                    {rail.badge}
                  </span>
                </div>
                <dl className="space-y-3 text-sm leading-relaxed">
                  <div>
                    <dt className="text-slate-500 font-mono uppercase tracking-wider text-[10px]">
                      Auth header
                    </dt>
                    <dd className="text-slate-200 mt-1">{rail.authHeader}</dd>
                  </div>
                  <div>
                    <dt className="text-slate-500 font-mono uppercase tracking-wider text-[10px]">
                      Money flow
                    </dt>
                    <dd className="text-slate-400 mt-1">{rail.moneyFlow}</dd>
                  </div>
                  <div>
                    <dt className="text-slate-500 font-mono uppercase tracking-wider text-[10px]">
                      Use when
                    </dt>
                    <dd className="text-slate-400 mt-1">{rail.useWhen}</dd>
                  </div>
                  <div>
                    <dt className="text-slate-500 font-mono uppercase tracking-wider text-[10px]">
                      Tradeoff
                    </dt>
                    <dd className="text-slate-400 mt-1">{rail.tradeoff}</dd>
                  </div>
                </dl>
              </article>
            ))}
          </div>
        </section>

        <section className="mb-16">
          <h2 className="font-display font-bold text-2xl text-slate-100 mb-4 tracking-tight">
            Agent route selection
          </h2>
          <p className="text-slate-400 leading-relaxed mb-8 max-w-3xl">
            If you are an agent reading this page, pick the path that matches
            your integration goal. The common rule across all four paths is the
            same: estimate first, then execute on the rail you actually mean to
            use.
          </p>

          <div className="grid gap-4 md:grid-cols-2">
            {agentPaths.map((path) => (
              <article
                key={path.title}
                className="bg-surface border border-slate-800 rounded-xl p-5"
              >
                <h3 className="font-display font-semibold text-lg text-slate-100 mb-2">
                  {path.title}
                </h3>
                <p className="text-slate-400 text-sm leading-relaxed mb-4">
                  {path.summary}
                </p>
                <ol className="space-y-2.5 text-sm text-slate-400 list-decimal list-inside">
                  {path.steps.map((step) => (
                    <li key={step}>{step}</li>
                  ))}
                </ol>
              </article>
            ))}
          </div>
        </section>

        <section className="bg-surface border border-amber/20 rounded-xl p-8">
          <div className="flex items-center gap-3 mb-4">
            <span className="text-xs font-mono font-semibold text-amber uppercase tracking-widest">
              Agent Metadata
            </span>
          </div>
          <h2 className="font-display font-bold text-xl text-slate-100 mb-4">
            Canonical instructions
          </h2>
          <p className="text-slate-400 text-sm leading-relaxed mb-6">
            Use this page to choose the right pricing rail. Use the links below
            for the machine-readable contract and the fuller onboarding path.
          </p>

          <div className="space-y-3">
            <div className="bg-elevated border border-slate-700 rounded-lg p-4 flex items-start gap-3">
              <span className="text-amber mt-0.5 text-xs">→</span>
              <div>
                <strong className="text-slate-200 text-sm">llms.txt</strong>
                <p className="text-slate-400 text-sm mt-0.5">
                  Machine-readable discovery: {" "}
                  <Link
                    href="/llms.txt"
                    className="text-amber hover:underline underline-offset-2 font-mono text-xs"
                  >
                    rhumb.dev/llms.txt
                  </Link>
                </p>
              </div>
            </div>

            <div className="bg-elevated border border-slate-700 rounded-lg p-4 flex items-start gap-3">
              <span className="text-amber mt-0.5 text-xs">→</span>
              <div>
                <strong className="text-slate-200 text-sm">API Documentation</strong>
                <p className="text-slate-400 text-sm mt-0.5">
                  Resolve mental model, estimate flow, and execution contract: {" "}
                  <Link
                    href="/docs#resolve-mental-model"
                    className="text-amber hover:underline underline-offset-2 font-mono text-xs"
                  >
                    rhumb.dev/docs#resolve-mental-model
                  </Link>
                </p>
              </div>
            </div>

            <div className="bg-elevated border border-slate-700 rounded-lg p-4 flex items-start gap-3">
              <span className="text-amber mt-0.5 text-xs">→</span>
              <div>
                <strong className="text-slate-200 text-sm">Wallet-first detail</strong>
                <p className="text-slate-400 text-sm mt-0.5">
                  Wallet-prefund and x402 specifics live here: {" "}
                  <Link
                    href="/payments/agent"
                    className="text-amber hover:underline underline-offset-2 font-mono text-xs"
                  >
                    rhumb.dev/payments/agent
                  </Link>
                </p>
              </div>
            </div>

            <div className="bg-elevated border border-slate-700 rounded-lg p-4 flex items-start gap-3">
              <span className="text-amber mt-0.5 text-xs">→</span>
              <div>
                <strong className="text-slate-200 text-sm">MCP Server</strong>
                <p className="text-slate-400 text-sm mt-0.5">
                  Use MCP when you want Rhumb inside an agent loop instead of
                  wiring raw HTTP yourself.
                </p>
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}

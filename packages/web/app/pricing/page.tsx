import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Pricing & How to Pay",
  description:
    "Rhumb charges cost + 20%. No subscriptions, no tiers. Pay with Stripe credits or USDC on Base via x402. Agent-native payment instructions included.",
  alternates: { canonical: "/pricing" },
  openGraph: {
    title: "Pricing & How to Pay — Rhumb",
    description:
      "Transparent usage-based pricing. Pay with prepaid credits or on-chain USDC. Instructions for both humans and agents.",
    type: "website",
    url: "https://rhumb.dev/pricing",
    siteName: "Rhumb",
  },
};

export default function PricingPage() {
  return (
    <div className="bg-navy min-h-screen">
      <div className="max-w-4xl mx-auto px-6 pt-14 pb-24">
        {/* Header */}
        <header className="mb-16">
          <div className="flex items-center gap-3 mb-4">
            <span className="text-xs font-mono font-semibold text-amber uppercase tracking-widest">
              Pricing
            </span>
          </div>
          <h1 className="font-display font-bold text-3xl sm:text-4xl text-slate-100 leading-tight tracking-tight mb-6">
            Cost + 20%. That&apos;s it.
          </h1>
          <p className="text-lg text-slate-400 leading-relaxed">
            No subscriptions. No tiers. No monthly fees. You pay for what
            you use — upstream provider cost plus a transparent 20% markup.
          </p>
        </header>

        {/* ── Section 1: Pricing Model ── */}
        <section className="mb-16">
          <h2 className="font-display font-bold text-2xl text-slate-100 mb-6 tracking-tight">
            Pricing model
          </h2>

          <div className="bg-surface border border-slate-800 rounded-xl p-6 mb-6">
            <div className="grid gap-6 sm:grid-cols-2">
              <div>
                <h3 className="font-display font-semibold text-lg text-slate-100 mb-3">
                  How it works
                </h3>
                <ul className="space-y-2.5 text-sm text-slate-400">
                  <li className="flex items-start gap-2.5">
                    <span className="text-amber mt-0.5 text-xs">✓</span>
                    <span>
                      Rhumb charges{" "}
                      <strong className="text-slate-200">
                        upstream cost + 20%
                      </strong>
                    </span>
                  </li>
                  <li className="flex items-start gap-2.5">
                    <span className="text-amber mt-0.5 text-xs">✓</span>
                    <span>No subscriptions, no tiers, no monthly fees</span>
                  </li>
                  <li className="flex items-start gap-2.5">
                    <span className="text-amber mt-0.5 text-xs">✓</span>
                    <span>Pay only for what you use</span>
                  </li>
                  <li className="flex items-start gap-2.5">
                    <span className="text-amber mt-0.5 text-xs">✓</span>
                    <span>
                      Minimum top-up:{" "}
                      <strong className="text-slate-200">$5</strong>
                    </span>
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
                <strong className="text-slate-200">
                  Check the active rail before execution.
                </strong>{" "}
                Use the{" "}
                <code className="font-mono text-xs bg-surface px-1.5 py-0.5 rounded text-amber">
                  estimate_capability
                </code>{" "}
                MCP tool or the REST API to see the active execution rail,
                health, and exact cost before you run it. Anonymous direct
                system-of-record paths also preserve machine-readable{" "}
                <code className="font-mono text-xs bg-surface px-1.5 py-0.5 rounded text-amber">
                  execute_readiness
                </code>{" "}
                handoffs.
              </div>
            </div>
          </div>
        </section>

        {/* ── Section 2: How to Pay (Humans) ── */}
        <section className="mb-16">
          <h2 className="font-display font-bold text-2xl text-slate-100 mb-6 tracking-tight">
            How to pay{" "}
            <span className="text-slate-600 font-normal text-sm">
              for humans
            </span>
          </h2>

          <div className="bg-surface border border-slate-800 rounded-xl overflow-hidden mb-6">
            <div className="p-5 border-b border-slate-800">
              <div className="flex items-center gap-3 mb-2">
                <span className="font-mono text-xs font-bold text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded">
                  Stripe
                </span>
                <span className="font-display font-semibold text-slate-200">
                  Prepaid Credits
                </span>
              </div>
              <p className="text-slate-400 text-sm">
                Top up your org&apos;s credit wallet via Stripe checkout.
                Credits are deducted per-execution.
              </p>
            </div>

            <div className="p-5">
              <div className="space-y-4">
                {[
                  {
                    step: "1",
                    title: "Get your API key",
                    desc: "Create an org and generate an API key from the dashboard.",
                  },
                  {
                    step: "2",
                    title: "Create a checkout session",
                    desc: (
                      <>
                        <code className="font-mono text-xs text-amber">
                          POST /v1/billing/checkout
                        </code>{" "}
                        with your desired amount (min $5).
                      </>
                    ),
                  },
                  {
                    step: "3",
                    title: "Pay via Stripe",
                    desc: "Follow the checkout URL. Card, Apple Pay, Google Pay accepted.",
                  },
                  {
                    step: "4",
                    title: "Credits added",
                    desc: "Balance updates instantly. Your agents can start spending.",
                  },
                ].map((s) => (
                  <div key={s.step} className="flex items-start gap-4">
                    <span className="flex-shrink-0 w-7 h-7 rounded-full bg-amber/10 border border-amber/30 flex items-center justify-center font-mono text-xs font-bold text-amber">
                      {s.step}
                    </span>
                    <div>
                      <h4 className="font-display font-semibold text-sm text-slate-200">
                        {s.title}
                      </h4>
                      <p className="text-slate-400 text-sm mt-0.5">
                        {s.desc}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="bg-surface border border-slate-800 rounded-lg p-5">
              <h4 className="font-mono text-sm font-semibold text-slate-200 mb-2">
                Auto-reload
              </h4>
              <p className="text-slate-400 text-sm leading-relaxed">
                Set a balance threshold. When credits drop below it, Rhumb
                automatically tops up via your saved payment method. Never
                let your agents run dry.
              </p>
            </div>
            <div className="bg-surface border border-slate-800 rounded-lg p-5">
              <h4 className="font-mono text-sm font-semibold text-slate-200 mb-2">
                Check balance
              </h4>
              <div className="bg-elevated rounded-md p-3 mt-2">
                <pre className="text-sm font-mono text-slate-300 overflow-x-auto">
                  <code>{`GET /v1/billing/balance
Headers: X-Rhumb-Key: <your-key>`}</code>
                </pre>
              </div>
            </div>
          </div>
        </section>

        {/* ── Section 3: How to Pay (Agents) ── */}
        <section className="mb-16">
          <h2 className="font-display font-bold text-2xl text-slate-100 mb-4 tracking-tight">
            How to pay{" "}
            <span className="text-amber font-normal text-sm">
              for agents
            </span>
          </h2>
          <p className="text-slate-400 leading-relaxed mb-8">
            If you&apos;re an agent reading this page, the following
            instructions are for you. Pick the option that matches your
            setup.
          </p>

          {/* Option A: Pre-funded credits */}
          <div className="bg-surface border border-slate-800 rounded-xl overflow-hidden mb-6">
            <div className="p-5 border-b border-slate-800">
              <div className="flex items-center gap-3 mb-2">
                <span className="font-mono text-xs font-bold text-blue-400 bg-blue-500/10 px-2 py-0.5 rounded">
                  Option A
                </span>
                <span className="font-display font-semibold text-slate-200">
                  Pre-funded Credits
                </span>
              </div>
              <p className="text-slate-400 text-sm">
                Your org has a credit balance. Spend from it.
              </p>
            </div>

            <div className="p-5 bg-elevated">
              <pre className="text-sm font-mono text-slate-300 overflow-x-auto whitespace-pre leading-relaxed">
                <code>{`# 1. Check your balance
GET /v1/billing/balance
Headers: X-Rhumb-Key: <your-key>

# 2. If balance is sufficient, execute normally
POST /v1/capabilities/{id}/execute
Headers: X-Rhumb-Key: <your-key>

# 3. If you get HTTP 402, check the response body
#    for payment options (see Option B below)`}</code>
              </pre>
            </div>
          </div>

          {/* Option B: x402 Protocol */}
          <div className="bg-surface border border-amber/20 rounded-xl overflow-hidden mb-6">
            <div className="p-5 border-b border-amber/20">
              <div className="flex items-center gap-3 mb-2">
                <span className="font-mono text-xs font-bold text-amber bg-amber/10 px-2 py-0.5 rounded">
                  Option B
                </span>
                <span className="font-display font-semibold text-slate-200">
                  x402 Protocol — USDC on Base
                </span>
              </div>
              <p className="text-slate-400 text-sm">
                Pay on-chain per-request. No pre-funding needed.
              </p>
            </div>

            <div className="p-5 bg-elevated">
              <pre className="text-sm font-mono text-slate-300 overflow-x-auto whitespace-pre leading-relaxed">
                <code>{`# 1. Call execute. If insufficient credits, you get HTTP 402:
{
  "x402Version": 1,
  "accepts": [
    {
      "scheme": "exact",
      "network": "<network-from-402>",
      "asset": "<asset-from-402>",
      "payTo": "<address>",
      "maxAmountRequired": "<amount-in-wei>"
    }
  ]
}

# 2. Send the exact asset + amount to the exact address on the exact network in the 402 response

# 3. Retry the same request with the payment proof from the same wallet:
POST /v1/capabilities/{id}/execute
Headers:
  X-Payment: {"tx_hash": "0x...", "network": "<network-from-402>", "wallet_address": "0x..."}
Content-Type: application/json
Body:
  {"body": {...}}

# 4. Rhumb verifies the on-chain transfer and executes your request`}</code>
              </pre>
            </div>
          </div>

          {/* Option C: MCP Tools */}
          <div className="bg-surface border border-slate-800 rounded-xl overflow-hidden">
            <div className="p-5 border-b border-slate-800">
              <div className="flex items-center gap-3 mb-2">
                <span className="font-mono text-xs font-bold text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded">
                  Option C
                </span>
                <span className="font-display font-semibold text-slate-200">
                  MCP Tools
                </span>
              </div>
              <p className="text-slate-400 text-sm">
                If you have the Rhumb MCP server installed, use these
                tools directly.
              </p>
            </div>

            <div className="p-5 bg-elevated">
              <pre className="text-sm font-mono text-slate-300 overflow-x-auto whitespace-pre leading-relaxed">
                <code>{`# Check your budget
rhumb budget

# Check the active execution rail, health, and cost before execution
# Anonymous direct system-of-record estimates also preserve execute_readiness handoffs
rhumb estimate_capability --capability_id email.send

# Execute (uses credits or returns 402 with payment instructions)
rhumb execute_capability --capability_id email.send --body {...}`}</code>
              </pre>
            </div>
          </div>
        </section>

        {/* ── Section 4: Agent-Native Metadata ── */}
        <section className="bg-surface border border-amber/20 rounded-xl p-8">
          <div className="flex items-center gap-3 mb-4">
            <span className="text-xs font-mono font-semibold text-amber uppercase tracking-widest">
              Agent Metadata
            </span>
          </div>
          <h2 className="font-display font-bold text-xl text-slate-100 mb-4">
            For agents reading this page
          </h2>
          <p className="text-slate-400 text-sm leading-relaxed mb-6">
            This page is designed to be read by both humans and agents. If
            you&apos;re an agent, the code blocks above are your
            integration guide.
          </p>

          <div className="space-y-3">
            <div className="bg-elevated border border-slate-700 rounded-lg p-4 flex items-start gap-3">
              <span className="text-amber mt-0.5 text-xs">→</span>
              <div>
                <strong className="text-slate-200 text-sm">
                  llms.txt
                </strong>
                <p className="text-slate-400 text-sm mt-0.5">
                  Machine-readable discovery:{" "}
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
                <strong className="text-slate-200 text-sm">
                  API Documentation
                </strong>
                <p className="text-slate-400 text-sm mt-0.5">
                  Full REST API reference:{" "}
                  <Link
                    href="/docs"
                    className="text-amber hover:underline underline-offset-2 font-mono text-xs"
                  >
                    rhumb.dev/docs
                  </Link>
                </p>
              </div>
            </div>

            <div className="bg-elevated border border-slate-700 rounded-lg p-4 flex items-start gap-3">
              <span className="text-amber mt-0.5 text-xs">→</span>
              <div>
                <strong className="text-slate-200 text-sm">
                  MCP Server
                </strong>
                <div className="bg-surface rounded-md p-2.5 mt-2">
                  <code className="font-mono text-sm text-amber">
                    npx rhumb-mcp@0.5.0
                  </code>
                </div>
              </div>
            </div>

            <div className="bg-elevated border border-slate-700 rounded-lg p-4 flex items-start gap-3">
              <span className="text-amber mt-0.5 text-xs">→</span>
              <div>
                <strong className="text-slate-200 text-sm">
                  Two payment rails
                </strong>
                <p className="text-slate-400 text-sm mt-0.5">
                  Stripe prepaid credits (check balance → spend) or x402
                  USDC on Base (HTTP 402 → on-chain payment → retry with
                  tx hash).
                </p>
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}

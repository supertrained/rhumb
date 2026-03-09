import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Why Stripe Scores 8.3 and PayPal Scores 5.2 for AI Agents | Rhumb",
  description:
    "We scored 6 payment APIs on how well they work for AI agents — not humans. The results surprised us.",
  alternates: { canonical: "/blog/payments-for-agents" },
  openGraph: {
    title: "Why Stripe Scores 8.3 and PayPal Scores 5.2 for AI Agents",
    description:
      "We scored 6 payment APIs on how well they work for AI agents. The most popular one scored worst.",
    type: "article",
    publishedTime: "2026-03-09T00:00:00Z",
    authors: ["Pedro Nunes"],
    images: [{ url: "/blog/payments-for-agents/og", width: 1200, height: 630 }],
  },
};

// Payment tool data (from Rhumb AN Score v0.2)
const TOOLS = [
  {
    name: "Stripe",
    slug: "stripe",
    agg: 8.3,
    exec: 9.0,
    access: 6.6,
    tier: "L4",
    tierLabel: "Native",
    p50: 120,
    whyHigh:
      "Idempotency keys on every endpoint. Structured JSON errors with machine-readable codes. Webhook signatures with replay protection. API versioning via header — no URL breakage.",
    whyLow:
      "OAuth onboarding for Connect still requires human-in-the-loop. Dashboard-only features (dispute management, radar rules) have no API equivalent.",
  },
  {
    name: "Lemon Squeezy",
    slug: "lemon-squeezy",
    agg: 7.0,
    exec: 7.5,
    access: 5.7,
    tier: "L3",
    tierLabel: "Ready",
    p50: 105,
    whyHigh:
      "Clean REST API with consistent JSON responses. Good webhook support. Simple API key auth — no OAuth dance required.",
    whyLow:
      "Limited programmatic control over store setup. No idempotency keys. Error messages are human-readable strings, not machine-parseable codes. Fewer integration patterns than Stripe.",
  },
  {
    name: "Square",
    slug: "square",
    agg: 6.7,
    exec: 7.3,
    access: 5.2,
    tier: "L3",
    tierLabel: "Ready",
    p50: 140,
    whyHigh:
      "Solid SDK coverage. Idempotency keys available on create endpoints. GraphQL option for flexible queries.",
    whyLow:
      "OAuth flow mandatory for marketplace integrations. SDK error types inconsistent across languages. Higher latency on batch operations.",
  },
  {
    name: "Adyen",
    slug: "adyen",
    agg: 6.5,
    exec: 7.3,
    access: 4.7,
    tier: "L3",
    tierLabel: "Ready",
    p50: 155,
    whyHigh:
      "Enterprise-grade reliability. Comprehensive webhook events. Strong idempotency support.",
    whyLow:
      "Onboarding requires human sales contact. Test environment setup is manual. Documentation assumes human readers with prior payment domain knowledge.",
  },
  {
    name: "Braintree",
    slug: "braintree",
    agg: 5.8,
    exec: 6.5,
    access: 4.3,
    tier: "L2",
    tierLabel: "Developing",
    p50: 185,
    whyHigh:
      "PayPal ecosystem integration. Mature SDK with good type coverage.",
    whyLow:
      "XML error responses in some endpoints. Complex sandbox provisioning. Rate limits are opaque (no Retry-After header). Legacy API patterns mixed with modern ones.",
  },
  {
    name: "PayPal",
    slug: "paypal",
    agg: 5.2,
    exec: 5.9,
    access: 3.7,
    tier: "L2",
    tierLabel: "Developing",
    p50: 210,
    whyHigh:
      "Ubiquitous — virtually every user already has an account. REST API exists and covers core flows.",
    whyLow:
      "Error responses mix human strings with codes inconsistently. OAuth token rotation has undocumented edge cases. Webhook verification requires fetching a signing cert chain. Rate limits enforced silently (requests just fail). P50 latency 2x higher than Stripe. Sandbox environment frequently diverges from production behavior.",
  },
];

function tierColor(tier: string): string {
  switch (tier) {
    case "L4":
      return "#7c3aed";
    case "L3":
      return "#059669";
    case "L2":
      return "#2563eb";
    case "L1":
      return "#6b7280";
    default:
      return "#0f172a";
  }
}

export default function PaymentsForAgents() {
  return (
    <article style={{ maxWidth: 720, margin: "0 auto", padding: "40px 20px" }}>
      <header>
        <p style={{ color: "#7c3aed", fontWeight: 600, fontSize: 14, marginBottom: 8 }}>
          TOOL AUTOPSY
        </p>
        <h1 style={{ fontSize: 32, lineHeight: 1.2, marginBottom: 16 }}>
          Why Stripe Scores 8.3 and PayPal Scores 5.2 for AI Agents
        </h1>
        <p style={{ color: "#64748b", fontSize: 15, marginBottom: 32 }}>
          We scored 6 payment APIs on how well they work for AI agents — not humans.
          The most popular one scored the worst.{" "}
          <span style={{ color: "#94a3b8" }}>March 9, 2026 · Pedro Nunes</span>
        </p>
      </header>

      {/* Intro */}
      <section style={{ marginBottom: 40, lineHeight: 1.7, fontSize: 16 }}>
        <p>
          When a human picks a payment processor, they compare pricing pages, read case studies,
          and ask their network. When an AI agent picks one, it needs to know: <em>Can I call this
          API without getting stuck?</em>
        </p>
        <p style={{ marginTop: 16 }}>
          &quot;Great documentation&quot; means nothing when your user is a language model. What
          matters is: Are errors machine-readable? Are operations idempotent? Can I retry safely
          without human intervention?
        </p>
        <p style={{ marginTop: 16 }}>
          We built the{" "}
          <Link href="/leaderboard/payments" style={{ color: "#7c3aed", textDecoration: "underline" }}>
            Agent-Native Score
          </Link>{" "}
          to answer this. Here&apos;s what we found when we scored the 6 most common payment
          APIs that agents actually use.
        </p>
      </section>

      {/* Leaderboard summary */}
      <section style={{ marginBottom: 40 }}>
        <h2 style={{ fontSize: 22, marginBottom: 16 }}>The Leaderboard</h2>
        <div
          style={{
            border: "1px solid #e2e8f0",
            borderRadius: 12,
            overflow: "hidden",
          }}
        >
          {TOOLS.map((tool, i) => (
            <div
              key={tool.slug}
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                padding: "16px 20px",
                borderBottom: i < TOOLS.length - 1 ? "1px solid #f1f5f9" : "none",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                <span
                  style={{ fontWeight: 700, fontSize: 14, color: "#94a3b8", width: 24 }}
                >
                  #{i + 1}
                </span>
                <Link
                  href={`/service/${tool.slug}`}
                  style={{
                    fontWeight: 600,
                    color: "#0f172a",
                    textDecoration: "none",
                    fontSize: 16,
                  }}
                >
                  {tool.name}
                </Link>
                <span
                  style={{
                    fontSize: 12,
                    color: tierColor(tool.tier),
                    border: `1px solid ${tierColor(tool.tier)}`,
                    borderRadius: 999,
                    padding: "1px 8px",
                  }}
                >
                  {tool.tier} {tool.tierLabel}
                </span>
              </div>
              <span style={{ fontWeight: 700, fontSize: 20, color: "#0f172a" }}>
                {tool.agg.toFixed(1)}
              </span>
            </div>
          ))}
        </div>
        <p style={{ marginTop: 12, fontSize: 13, color: "#94a3b8" }}>
          Agent-Native Score v0.2 · Execution (70%) + Access (30%) · Higher is better ·{" "}
          <Link href="/leaderboard/payments" style={{ color: "#7c3aed" }}>
            Full leaderboard →
          </Link>
        </p>
      </section>

      {/* Individual breakdowns */}
      {TOOLS.map((tool) => (
        <section key={tool.slug} style={{ marginBottom: 48 }}>
          <h2 style={{ fontSize: 20, marginBottom: 8 }}>
            <Link
              href={`/service/${tool.slug}`}
              style={{ color: "#0f172a", textDecoration: "none" }}
            >
              {tool.name}
            </Link>{" "}
            <span style={{ color: tierColor(tool.tier), fontWeight: 400, fontSize: 16 }}>
              {tool.agg.toFixed(1)} · {tool.tier}
            </span>
          </h2>

          <div
            style={{
              display: "flex",
              gap: 16,
              marginBottom: 16,
              fontSize: 14,
              color: "#475569",
            }}
          >
            <span>
              Execution: <strong>{tool.exec.toFixed(1)}</strong>
            </span>
            <span>
              Access: <strong>{tool.access.toFixed(1)}</strong>
            </span>
            <span>
              P50 latency: <strong>{tool.p50}ms</strong>
            </span>
          </div>

          <div style={{ lineHeight: 1.7, fontSize: 15 }}>
            <p>
              <strong style={{ color: "#059669" }}>What works for agents:</strong>{" "}
              {tool.whyHigh}
            </p>
            <p style={{ marginTop: 8 }}>
              <strong style={{ color: "#dc2626" }}>Where agents get stuck:</strong>{" "}
              {tool.whyLow}
            </p>
          </div>
        </section>
      ))}

      {/* Key insight */}
      <section
        style={{
          marginBottom: 40,
          padding: 24,
          background: "#f8fafc",
          borderRadius: 12,
          borderLeft: "4px solid #7c3aed",
        }}
      >
        <h2 style={{ fontSize: 18, marginBottom: 12, color: "#7c3aed" }}>
          The Pattern
        </h2>
        <div style={{ lineHeight: 1.7, fontSize: 15 }}>
          <p>
            The gap between Stripe (8.3) and PayPal (5.2) isn&apos;t about features — both
            process payments. It&apos;s about <strong>execution ergonomics</strong>: idempotency,
            structured errors, retry safety, and predictable latency.
          </p>
          <p style={{ marginTop: 12 }}>
            Stripe was built API-first. PayPal was built for checkout buttons and added an API
            later. That architectural decision from 2011 still shows up in every agent interaction
            in 2026.
          </p>
          <p style={{ marginTop: 12 }}>
            For AI automation teams: if your agent is spending tokens parsing error messages or
            implementing custom retry logic, the tool isn&apos;t saving you time. It&apos;s
            costing you compute.
          </p>
        </div>
      </section>

      {/* Methodology */}
      <section style={{ marginBottom: 40 }}>
        <h2 style={{ fontSize: 18, marginBottom: 12 }}>Methodology</h2>
        <div style={{ lineHeight: 1.7, fontSize: 15, color: "#475569" }}>
          <p>
            The <strong>Agent-Native Score</strong> evaluates tools across 17 dimensions grouped into
            Execution (how well the API works when called) and Access (how easy it is for an agent
            to start using it autonomously). Scores are weighted 70/30 Execution/Access.
          </p>
          <p style={{ marginTop: 12 }}>
            Key dimensions include: schema stability, error ergonomics, idempotency guarantees,
            latency distribution (P50/P95/P99), cold-start behavior, token cost of integration,
            and graceful degradation under load.
          </p>
          <p style={{ marginTop: 12 }}>
            All scores are based on live probe data, not documentation review.{" "}
            <Link href="/leaderboard/payments" style={{ color: "#7c3aed" }}>
              View the full payments leaderboard →
            </Link>
          </p>
        </div>
      </section>

      {/* CTA */}
      <section
        style={{
          padding: 24,
          border: "1px solid #e2e8f0",
          borderRadius: 12,
          textAlign: "center",
        }}
      >
        <h2 style={{ fontSize: 18, marginBottom: 8 }}>
          Want to see how your tools stack up?
        </h2>
        <p style={{ color: "#64748b", marginBottom: 16 }}>
          We&apos;ve scored 50 developer tools across 10 categories.
        </p>
        <Link
          href="/leaderboard"
          style={{
            display: "inline-block",
            padding: "10px 24px",
            background: "#7c3aed",
            color: "white",
            borderRadius: 8,
            textDecoration: "none",
            fontWeight: 600,
          }}
        >
          Browse all categories →
        </Link>
      </section>
    </article>
  );
}

import React from "react";
import Link from "next/link";
import { notFound } from "next/navigation";

import { getServiceScore } from "../../../lib/api";
import type { ServiceScoreViewModel } from "../../../lib/types";

function scoreLabel(value: number | null): string {
  return value === null ? "Pending" : value.toFixed(1);
}

function freshnessLabel(score: ServiceScoreViewModel): string {
  if (score.evidenceFreshness) {
    return score.evidenceFreshness;
  }

  if (score.calculatedAt) {
    return `Updated ${score.calculatedAt}`;
  }

  return "Freshness pending";
}

export default async function ServicePage({
  params
}: {
  params: Promise<{ slug: string }>;
}): Promise<JSX.Element> {
  const { slug } = await params;
  const score = await getServiceScore(slug);

  if (score === null) {
    notFound();
  }

  return (
    <section>
      <h1>{score.serviceSlug}</h1>
      <p style={{ marginTop: 8, color: "#475569" }}>Freshness: {freshnessLabel(score)}</p>

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 12 }}>
        <strong
          style={{
            padding: "4px 10px",
            borderRadius: 999,
            background: "#0f172a",
            color: "#fff"
          }}
        >
          Aggregate {scoreLabel(score.aggregateRecommendationScore)}
        </strong>
        <span style={{ padding: "4px 10px", borderRadius: 999, border: "1px solid #cbd5e1" }}>
          Execution {scoreLabel(score.executionScore)}
        </span>
        <span style={{ padding: "4px 10px", borderRadius: 999, border: "1px solid #cbd5e1" }}>
          Access {scoreLabel(score.accessReadinessScore)}
        </span>
      </div>

      <p style={{ marginTop: 12 }}>
        Tier: <strong>{score.tierLabel ?? score.tier ?? "Pending"}</strong>
        {score.confidence !== null ? ` · Confidence ${score.confidence.toFixed(2)}` : ""}
      </p>

      <p>{score.explanation ?? "Explanation pending."}</p>

      <section style={{ marginTop: 20 }}>
        <h2 style={{ marginBottom: 8 }}>Active failure modes</h2>
        {score.activeFailures.length > 0 ? (
          <ul style={{ marginTop: 0 }}>
            {score.activeFailures.map((failure) => (
              <li key={failure.id ?? failure.summary}>{failure.summary}</li>
            ))}
          </ul>
        ) : (
          <p style={{ marginTop: 0 }}>No active failure modes reported.</p>
        )}
      </section>

      <section style={{ marginTop: 20 }}>
        <h2 style={{ marginBottom: 8 }}>Alternatives</h2>
        {score.alternatives.length > 0 ? (
          <ul style={{ marginTop: 0 }}>
            {score.alternatives.map((alternative) => (
              <li key={alternative.serviceSlug}>
                <Link href={`/service/${alternative.serviceSlug}`}>{alternative.serviceSlug}</Link>
                {alternative.score !== null ? ` (${alternative.score.toFixed(1)})` : ""}
              </li>
            ))}
          </ul>
        ) : (
          <p style={{ marginTop: 0 }}>No alternatives captured yet.</p>
        )}
      </section>
    </section>
  );
}

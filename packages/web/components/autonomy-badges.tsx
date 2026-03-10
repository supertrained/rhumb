import React from "react";

export type AutonomyBadgesProps = {
  p1Score: number | null;
  g1Score: number | null;
  w1Score: number | null;
};

/** Returns ✓ or ✗ for binary pass/fail dimensions (P1, G1). */
function binarySymbol(score: number | null): string {
  if (score === null) return "—";
  return score >= 5.0 ? "✓" : "✗";
}

/** Returns circle fill symbols for continuous W1 dimension. */
function w1Symbol(score: number | null): string {
  if (score === null) return "—";
  if (score >= 8.0) return "◕";
  if (score >= 6.0) return "◑";
  return "◐";
}

function p1Color(score: number | null): string {
  if (score === null) return "text-slate-500";
  return score >= 5.0 ? "text-score-native" : "text-score-limited";
}

function g1Color(score: number | null): string {
  if (score === null) return "text-slate-500";
  return score >= 5.0 ? "text-score-native" : "text-score-limited";
}

function w1Color(score: number | null): string {
  if (score === null) return "text-slate-500";
  if (score >= 8.0) return "text-score-native";
  if (score >= 6.0) return "text-score-ready";
  return "text-amber";
}

function scoreLabel(score: number | null): string {
  return score !== null ? `${score.toFixed(1)}/10` : "N/A";
}

/**
 * Autonomy micro-badges for leaderboard cards.
 * Shows P1 (Payment Autonomy), G1 (Governance Readiness), W1 (Web Agent Accessibility)
 * as compact inline indicators with hover tooltips.
 */
export function AutonomyBadges({ p1Score, g1Score, w1Score }: AutonomyBadgesProps): JSX.Element {
  return (
    <div
      className="flex items-center gap-3 text-xs font-mono"
      aria-label="Autonomy indicators"
      data-testid="autonomy-badges"
    >
      <span
        className={p1Color(p1Score)}
        title={`P1: Payment Autonomy (${scoreLabel(p1Score)}) — agent-native payment support`}
        aria-label={`Payment Autonomy: ${binarySymbol(p1Score)}`}
      >
        P1: {binarySymbol(p1Score)}
      </span>
      <span
        className={g1Color(g1Score)}
        title={`G1: Governance Readiness (${scoreLabel(g1Score)}) — RBAC, audit, compliance`}
        aria-label={`Governance Readiness: ${binarySymbol(g1Score)}`}
      >
        G1: {binarySymbol(g1Score)}
      </span>
      <span
        className={w1Color(w1Score)}
        title={`W1: Web Agent Accessibility (${scoreLabel(w1Score)}) — agent-navigable interfaces`}
        aria-label={`Web Agent Accessibility: ${w1Symbol(w1Score)}`}
      >
        W1: {w1Symbol(w1Score)}
      </span>
    </div>
  );
}

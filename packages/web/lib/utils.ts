/** Join CSS class tokens. */
export function cn(...tokens: Array<string | false | null | undefined>): string {
  return tokens.filter(Boolean).join(" ");
}

export type TierInfo = {
  /** Tailwind text color class */
  textClass: string;
  /** Tailwind bg class with opacity */
  bgClass: string;
  /** Tailwind border class with opacity */
  borderClass: string;
  /** CSS glow class (defined in globals.css) */
  glowClass: string;
  /** Raw hex color for inline use */
  hex: string;
  /** Short label e.g. "L4" */
  letter: string;
  /** Full label e.g. "L4 Native" */
  label: string;
  /** Tier key */
  tier: "native" | "ready" | "developing" | "limited" | "pending";
};

/** Derive tier display info from a numeric AN Score. */
export function getTierInfo(score: number | null): TierInfo {
  if (score === null) {
    return {
      textClass: "text-slate-500",
      bgClass: "bg-slate-800/50",
      borderClass: "border-slate-700/50",
      glowClass: "",
      hex: "#64748B",
      letter: "—",
      label: "Pending",
      tier: "pending",
    };
  }

  if (score >= 8.0) {
    return {
      textClass: "text-score-native",
      bgClass: "bg-score-native/10",
      borderClass: "border-score-native/30",
      glowClass: "glow-native",
      hex: "#10B981",
      letter: "L4",
      label: "L4 Native",
      tier: "native",
    };
  }

  if (score >= 7.0) {
    return {
      textClass: "text-score-ready",
      bgClass: "bg-score-ready/10",
      borderClass: "border-score-ready/30",
      glowClass: "glow-ready",
      hex: "#3B82F6",
      letter: "L3",
      label: "L3 Ready",
      tier: "ready",
    };
  }

  if (score >= 6.0) {
    return {
      textClass: "text-amber",
      bgClass: "bg-amber/10",
      borderClass: "border-amber/30",
      glowClass: "glow-developing",
      hex: "#F59E0B",
      letter: "L2",
      label: "L2 Developing",
      tier: "developing",
    };
  }

  return {
    textClass: "text-score-limited",
    bgClass: "bg-score-limited/10",
    borderClass: "border-score-limited/30",
    glowClass: "glow-limited",
    hex: "#EF4444",
    letter: "L1",
    label: "L1 Limited",
    tier: "limited",
  };
}

/** Derive tier info from a tier string (e.g. "L4", "native", "L3 Ready", etc.). */
export function getTierInfoFromString(tier: string | null): TierInfo {
  if (!tier) return getTierInfo(null);

  const upper = tier.toUpperCase();
  if (upper.startsWith("L4") || upper === "NATIVE") return getTierInfo(8.5);
  if (upper.startsWith("L3") || upper === "READY") return getTierInfo(7.5);
  if (upper.startsWith("L2") || upper === "DEVELOPING") return getTierInfo(6.5);
  if (upper.startsWith("L1") || upper === "LIMITED" || upper === "EMERGING") return getTierInfo(5.0);
  return getTierInfo(null);
}

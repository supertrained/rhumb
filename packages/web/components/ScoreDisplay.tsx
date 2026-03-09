import React from "react";
import { getTierInfo, getTierInfoFromString } from "../lib/utils";

type ScoreSize = "large" | "medium" | "small";

type ScoreProps = {
  score: number | null;
  size?: ScoreSize;
  showLabel?: boolean;
};

const sizeConfig = {
  large: {
    wrapper: "w-20 h-20",
    score: "text-3xl",
    label: "text-xs mt-1",
    border: "border-2",
  },
  medium: {
    wrapper: "w-14 h-14",
    score: "text-xl",
    label: "text-[10px] mt-0.5",
    border: "border-2",
  },
  small: {
    wrapper: "w-10 h-10",
    score: "text-sm",
    label: "hidden",
    border: "border",
  },
};

/** AN Score badge — tier-colored circular badge with glow effect. */
export function ScoreDisplay({ score, size = "medium", showLabel = true }: ScoreProps): JSX.Element {
  const tier = getTierInfo(score);
  const config = sizeConfig[size];

  return (
    <div
      className={[
        "relative flex flex-col items-center justify-center rounded-full shrink-0",
        config.wrapper,
        config.border,
        tier.bgClass,
        tier.borderClass,
        tier.glowClass,
      ].join(" ")}
    >
      <span className={`font-mono font-bold leading-none ${config.score} ${tier.textClass}`}>
        {score !== null ? score.toFixed(1) : "—"}
      </span>
      {showLabel && (
        <span className={`font-mono font-medium leading-none ${config.label} ${tier.textClass} opacity-80`}>
          {tier.letter}
        </span>
      )}
    </div>
  );
}

type TierBadgeProps = {
  tier: string | null;
  label?: string | null;
};

/** Inline tier pill — "L4 Native", "L3 Ready", etc. */
export function TierBadge({ tier, label }: TierBadgeProps): JSX.Element {
  const info = getTierInfoFromString(tier);

  return (
    <span
      className={[
        "inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-mono font-medium border",
        info.bgClass,
        info.borderClass,
        info.textClass,
      ].join(" ")}
    >
      {label ?? info.label}
    </span>
  );
}

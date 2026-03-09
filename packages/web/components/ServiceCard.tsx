import Link from "next/link";
import type { Service } from "../lib/types";
import { ScoreDisplay } from "./ScoreDisplay";

type Props = {
  service: Service;
  score?: number | null;
  tier?: string | null;
  executionScore?: number | null;
  accessScore?: number | null;
  freshness?: string | null;
  rank?: number;
};

/** Dark-surface service card with score badge, tier tag, hover effects. */
export function ServiceCard({
  service,
  score,
  tier,
  executionScore,
  accessScore,
  freshness,
  rank,
}: Props): JSX.Element {
  return (
    <Link href={`/service/${service.slug}`} className="block group">
      <article className="relative bg-surface border border-slate-800 rounded-xl p-5 transition-all duration-200 hover:border-slate-600 hover:bg-elevated hover:-translate-y-0.5">
        <div className="flex items-start gap-4">
          {/* Score badge */}
          {score !== undefined && (
            <ScoreDisplay score={score ?? null} size="medium" showLabel />
          )}

          {/* Content */}
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              {rank !== undefined && (
                <span className="font-mono text-xs text-slate-600 w-5 shrink-0">
                  #{rank}
                </span>
              )}
              <h3 className="font-display font-semibold text-slate-100 group-hover:text-amber transition-colors truncate">
                {service.name}
              </h3>
              {service.category && (
                <span className="text-xs text-slate-500 px-2 py-0.5 rounded-full border border-slate-800 bg-slate-900/50 shrink-0">
                  {service.category}
                </span>
              )}
            </div>

            {service.description && (
              <p className="mt-1 text-sm text-slate-400 leading-relaxed line-clamp-2">
                {service.description}
              </p>
            )}

            {/* Sub-scores */}
            {(executionScore !== undefined || accessScore !== undefined) && (
              <div className="mt-3 flex items-center gap-3 flex-wrap">
                {executionScore !== undefined && executionScore !== null && (
                  <span className="text-xs text-slate-500 font-mono">
                    Exec <span className="text-slate-300">{executionScore.toFixed(1)}</span>
                  </span>
                )}
                {accessScore !== undefined && accessScore !== null && (
                  <span className="text-xs text-slate-500 font-mono">
                    Access <span className="text-slate-300">{accessScore.toFixed(1)}</span>
                  </span>
                )}
                {tier && (
                  <span className="text-xs text-slate-600 font-mono">{tier}</span>
                )}
              </div>
            )}
          </div>
        </div>

        {freshness && (
          <p className="mt-3 text-xs text-slate-600 font-mono">{freshness}</p>
        )}
      </article>
    </Link>
  );
}

import { getTierInfo } from "../lib/utils";

type Dimension = {
  label: string;
  value: number | null;
};

type Props = {
  dimensions?: Dimension[];
};

/** Dimension score bars — displays per-dimension AN scores. */
export function DimensionChart({ dimensions }: Props): JSX.Element {
  if (!dimensions || dimensions.length === 0) {
    return (
      <div className="bg-surface border border-slate-800 rounded-xl p-6 text-sm text-slate-500 font-mono">
        Dimension breakdown available in a future release.
      </div>
    );
  }

  return (
    <div className="bg-surface border border-slate-800 rounded-xl p-6 space-y-4">
      {dimensions.map(({ label, value }) => {
        const tier = getTierInfo(value);
        const pct = value !== null ? Math.min((value / 10) * 100, 100) : 0;

        return (
          <div key={label}>
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-sm text-slate-300">{label}</span>
              <span className={`font-mono font-bold text-sm ${tier.textClass}`}>
                {value !== null ? value.toFixed(1) : "—"}
              </span>
            </div>
            <div className="h-1.5 bg-slate-800 rounded-full overflow-hidden">
              <div
                className="h-full rounded-full transition-all duration-700"
                style={{ width: `${pct}%`, backgroundColor: tier.hex }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}

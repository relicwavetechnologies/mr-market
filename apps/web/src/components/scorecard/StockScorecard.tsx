interface ScorecardMetric {
  label: string;
  value: number | null;
  format: "ratio" | "percent" | "currency";
  /** Thresholds: [good, warning]. Values below good are green, above warning are red. */
  thresholds?: [number, number];
  /** If true, lower is better (e.g., D/E ratio). */
  lowerIsBetter?: boolean;
}

interface Props {
  ticker: string;
  metrics: {
    pe: number | null;
    roe: number | null;
    roce: number | null;
    debtEquity: number | null;
  };
}

const METRIC_CONFIG: Array<Omit<ScorecardMetric, "value"> & { key: keyof Props["metrics"] }> = [
  { key: "pe", label: "P/E Ratio", format: "ratio", thresholds: [15, 30] },
  { key: "roe", label: "ROE", format: "percent", thresholds: [15, 25] },
  { key: "roce", label: "ROCE", format: "percent", thresholds: [15, 25] },
  { key: "debtEquity", label: "D/E Ratio", format: "ratio", thresholds: [0.5, 1.5], lowerIsBetter: true },
];

function getHealthColor(
  value: number | null,
  thresholds?: [number, number],
  lowerIsBetter?: boolean,
): string {
  if (value === null || !thresholds) return "text-gray-400";
  const [good, warning] = thresholds;

  if (lowerIsBetter) {
    if (value <= good) return "text-emerald-400";
    if (value <= warning) return "text-amber-400";
    return "text-red-400";
  }

  if (value >= warning) return "text-emerald-400";
  if (value >= good) return "text-amber-400";
  return "text-red-400";
}

function formatValue(value: number | null, format: string): string {
  if (value === null) return "--";
  if (format === "percent") return `${value.toFixed(1)}%`;
  return value.toFixed(2);
}

export function StockScorecard({ ticker, metrics }: Props) {
  return (
    <div className="rounded-xl border border-gray-700 bg-gray-900 p-4">
      <h3 className="mb-3 text-sm font-semibold text-gray-300">
        {ticker} Fundamental Scorecard
      </h3>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {METRIC_CONFIG.map(({ key, label, format, thresholds, lowerIsBetter }) => {
          const value = metrics[key];
          const color = getHealthColor(value, thresholds, lowerIsBetter);
          return (
            <div
              key={key}
              className="rounded-lg bg-gray-800 p-3 text-center"
            >
              <p className="text-xs text-gray-500">{label}</p>
              <p className={`mt-1 text-lg font-bold ${color}`}>
                {formatValue(value, format)}
              </p>
            </div>
          );
        })}
      </div>
    </div>
  );
}

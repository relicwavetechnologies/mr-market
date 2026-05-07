interface Props {
  rsi: number | null;
  macd: number | null;
  macdSignal: number | null;
}

function getRsiColor(rsi: number | null): string {
  if (rsi === null) return "text-gray-400";
  if (rsi >= 70) return "text-red-400";
  if (rsi <= 30) return "text-emerald-400";
  return "text-amber-400";
}

function getRsiLabel(rsi: number | null): string {
  if (rsi === null) return "--";
  if (rsi >= 70) return "Overbought";
  if (rsi <= 30) return "Oversold";
  return "Neutral";
}

export function IndicatorPanel({ rsi, macd, macdSignal }: Props) {
  const macdHistogram =
    macd !== null && macdSignal !== null ? macd - macdSignal : null;
  const macdColor =
    macdHistogram === null
      ? "text-gray-400"
      : macdHistogram > 0
        ? "text-emerald-400"
        : "text-red-400";

  return (
    <div className="grid grid-cols-2 gap-3 rounded-xl border border-gray-700 bg-gray-900 p-4">
      {/* RSI */}
      <div>
        <h4 className="text-xs font-medium text-gray-500">RSI (14)</h4>
        <div className="mt-1 flex items-baseline gap-2">
          <span className={`text-2xl font-bold ${getRsiColor(rsi)}`}>
            {rsi !== null ? rsi.toFixed(1) : "--"}
          </span>
          <span className={`text-xs ${getRsiColor(rsi)}`}>{getRsiLabel(rsi)}</span>
        </div>
        {/* RSI gauge bar */}
        <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-gray-800">
          <div
            className={`h-full rounded-full transition-all ${
              rsi !== null && rsi >= 70
                ? "bg-red-500"
                : rsi !== null && rsi <= 30
                  ? "bg-emerald-500"
                  : "bg-amber-500"
            }`}
            style={{ width: `${rsi ?? 0}%` }}
          />
        </div>
      </div>

      {/* MACD */}
      <div>
        <h4 className="text-xs font-medium text-gray-500">MACD</h4>
        <div className="mt-1 space-y-1">
          <div className="flex items-baseline justify-between">
            <span className="text-xs text-gray-500">Line</span>
            <span className="text-sm font-semibold text-gray-300">
              {macd !== null ? macd.toFixed(2) : "--"}
            </span>
          </div>
          <div className="flex items-baseline justify-between">
            <span className="text-xs text-gray-500">Signal</span>
            <span className="text-sm font-semibold text-gray-300">
              {macdSignal !== null ? macdSignal.toFixed(2) : "--"}
            </span>
          </div>
          <div className="flex items-baseline justify-between">
            <span className="text-xs text-gray-500">Histogram</span>
            <span className={`text-sm font-bold ${macdColor}`}>
              {macdHistogram !== null ? macdHistogram.toFixed(2) : "--"}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}

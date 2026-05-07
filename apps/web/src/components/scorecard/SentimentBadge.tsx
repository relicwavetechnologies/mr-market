import type { SentimentResult } from "@/types";

interface Props {
  sentiment: SentimentResult;
}

const VARIANT_STYLES: Record<SentimentResult["label"], string> = {
  Bullish: "bg-emerald-900/50 text-emerald-300 border-emerald-700",
  Bearish: "bg-red-900/50 text-red-300 border-red-700",
  Neutral: "bg-gray-800 text-gray-300 border-gray-600",
};

export function SentimentBadge({ sentiment }: Props) {
  const style = VARIANT_STYLES[sentiment.label];

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium ${style}`}
      title={`Score: ${sentiment.score.toFixed(2)} | Source: ${sentiment.source}`}
    >
      <span
        className={`h-1.5 w-1.5 rounded-full ${
          sentiment.label === "Bullish"
            ? "bg-emerald-400"
            : sentiment.label === "Bearish"
              ? "bg-red-400"
              : "bg-gray-400"
        }`}
      />
      {sentiment.label}
    </span>
  );
}

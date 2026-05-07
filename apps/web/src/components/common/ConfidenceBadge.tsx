interface Props {
  level: "HIGH" | "MEDIUM" | "LOW";
  source?: string;
}

const LEVEL_STYLES: Record<Props["level"], string> = {
  HIGH: "bg-emerald-900/50 text-emerald-300 border-emerald-700",
  MEDIUM: "bg-amber-900/50 text-amber-300 border-amber-700",
  LOW: "bg-red-900/50 text-red-300 border-red-700",
};

export function ConfidenceBadge({ level, source }: Props) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-[10px] font-medium uppercase ${LEVEL_STYLES[level]}`}
      title={source ? `Source: ${source}` : undefined}
    >
      {level} confidence
      {source && (
        <span className="ml-1 text-[9px] opacity-70">({source})</span>
      )}
    </span>
  );
}

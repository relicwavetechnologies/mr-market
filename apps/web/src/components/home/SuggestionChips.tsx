import {
  Sparkles,
  TrendingUp,
  BarChart3,
  Filter,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

interface Chip {
  icon: LucideIcon;
  label: string;
  query: string;
}

const CHIPS: Chip[] = [
  {
    icon: Sparkles,
    label: "For you",
    query: "",
  },
  {
    icon: TrendingUp,
    label: "Analyze a stock",
    query: "Give me a detailed analysis of Reliance Industries",
  },
  {
    icon: BarChart3,
    label: "Why is X moving?",
    query: "Why is Tata Motors falling today?",
  },
  {
    icon: Filter,
    label: "Screen stocks",
    query: "Show me undervalued IT stocks with RSI < 30",
  },
];

interface SuggestionChipsProps {
  onChipClick: (query: string) => void;
}

export function SuggestionChips({ onChipClick }: SuggestionChipsProps) {
  return (
    <div className="flex flex-wrap justify-center gap-2">
      {CHIPS.map((chip) => (
        <button
          key={chip.label}
          onClick={() => chip.query && onChipClick(chip.query)}
          className={`flex items-center gap-1.5 rounded-full border px-3.5 py-1.5 text-sm transition-colors ${
            !chip.query
              ? "border-accent/30 bg-accent/10 text-accent"
              : "border-border bg-bg-secondary text-text-secondary hover:border-text-muted hover:bg-bg-hover hover:text-text-primary"
          }`}
        >
          <chip.icon size={14} />
          <span>{chip.label}</span>
        </button>
      ))}
    </div>
  );
}

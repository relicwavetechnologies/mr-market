import { ArrowRight } from "lucide-react";

const SUGGESTIONS = [
  "Give me a trade setup for HDFC Bank",
  "Why is Tata Motors falling today?",
  "Show me undervalued IT stocks with RSI < 30",
  "What's the shareholding pattern of Zomato?",
];

interface PromptSuggestionsProps {
  onSuggestionClick: (prompt: string) => void;
}

export function PromptSuggestions({
  onSuggestionClick,
}: PromptSuggestionsProps) {
  return (
    <div className="w-full max-w-2xl space-y-1.5">
      {SUGGESTIONS.map((suggestion) => (
        <button
          key={suggestion}
          onClick={() => onSuggestionClick(suggestion)}
          className="group flex w-full items-center justify-between rounded-xl px-4 py-3 text-left text-sm text-text-secondary transition-colors hover:bg-bg-secondary"
        >
          <span className="transition-colors group-hover:text-text-primary">
            {suggestion}
          </span>
          <ArrowRight
            size={16}
            className="text-text-muted opacity-0 transition-all group-hover:text-text-secondary group-hover:opacity-100"
          />
        </button>
      ))}
    </div>
  );
}

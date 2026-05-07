import { useState } from "react";
import {
  Search,
  ArrowRight,
  Paperclip,
} from "lucide-react";
import { Dropdown } from "@/components/common/Dropdown";

const SEARCH_MODES = [
  { label: "Search", value: "search" },
  { label: "Deep Research", value: "deep" },
  { label: "Quick Answer", value: "quick" },
];

const MODEL_OPTIONS = [
  { label: "Gemini 2.5 Flash", value: "gemini-flash" },
  { label: "GPT-5.5", value: "gpt-5.5" },
  { label: "Gemini 2.5 Pro", value: "gemini-pro" },
];

interface SearchInputProps {
  onSubmit: (query: string) => void;
  placeholder?: string;
  initialValue?: string;
}

export function SearchInput({
  onSubmit,
  placeholder = "Ask anything about stocks...",
  initialValue = "",
}: SearchInputProps) {
  const [query, setQuery] = useState(initialValue);
  const [searchMode, setSearchMode] = useState("search");
  const [model, setModel] = useState("gemini-flash");

  const handleSubmit = () => {
    if (!query.trim()) return;
    onSubmit(query.trim());
    setQuery("");
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <div className="w-full max-w-2xl">
      <div className="rounded-2xl border border-border bg-bg-secondary transition-colors focus-within:border-text-muted">
        {/* Input area */}
        <div className="flex items-center px-4 py-3">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={placeholder}
            className="flex-1 bg-transparent text-sm text-text-primary placeholder-text-muted outline-none"
          />
        </div>

        {/* Toolbar */}
        <div className="flex items-center justify-between border-t border-border-subtle px-2 py-1.5">
          <div className="flex items-center gap-1">
            <button className="rounded-lg p-2 text-text-muted transition-colors hover:bg-bg-hover hover:text-text-secondary">
              <Paperclip size={16} />
            </button>
            <div className="h-4 w-px bg-border-subtle" />
            <Dropdown
              options={SEARCH_MODES}
              value={searchMode}
              onChange={setSearchMode}
            />
          </div>

          <div className="flex items-center gap-1">
            <Dropdown
              options={MODEL_OPTIONS}
              value={model}
              onChange={setModel}
            />
            <button
              onClick={handleSubmit}
              disabled={!query.trim()}
              className={`flex items-center justify-center rounded-full p-2 transition-colors ${
                query.trim()
                  ? "bg-accent text-white hover:bg-accent-hover"
                  : "bg-bg-hover text-text-muted"
              }`}
            >
              {query.trim() ? (
                <ArrowRight size={16} />
              ) : (
                <Search size={16} />
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

import { useRef, useState, type KeyboardEvent } from 'react';
import {
  ArrowUp,
  ChevronDown,
  Globe,
  Mic,
  Paperclip,
  Search,
  Telescope,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';

interface SearchInputProps {
  onSubmit: (query: string) => void;
  placeholder?: string;
  disabled?: boolean;
  autoFocus?: boolean;
  variant?: 'home' | 'chat';
}

const SEARCH_MODES = [
  { value: 'search', label: 'Search', icon: Search, hint: 'Quick web answers' },
  { value: 'research', label: 'Research', icon: Telescope, hint: 'Deep multi-source analysis' },
  { value: 'web', label: 'Web', icon: Globe, hint: 'Live news & filings' },
];

const MODELS = [
  { value: 'auto', label: 'Auto', hint: 'Best model for the query' },
  { value: 'gpt-5', label: 'GPT-5.5', hint: 'For complex reasoning' },
  { value: 'gemini', label: 'Gemini 2.5', hint: 'Fast, default' },
];

export function SearchInput({
  onSubmit,
  placeholder = 'Ask anything...',
  disabled = false,
  autoFocus = false,
  variant = 'home',
}: SearchInputProps) {
  const [value, setValue] = useState('');
  const [mode, setMode] = useState(SEARCH_MODES[0]);
  const [model, setModel] = useState(MODELS[0]);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleSubmit = () => {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSubmit(trimmed);
    setValue('');
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleInput = () => {
    const el = textareaRef.current;
    if (el) {
      el.style.height = 'auto';
      el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
    }
  };

  const hasValue = value.trim().length > 0;
  const ModeIcon = mode.icon;

  return (
    <div
      className={cn(
        'group relative w-full overflow-hidden rounded-2xl border border-border/80 bg-card shadow-[0_0_0_1px_rgb(0_0_0/0.04),0_8px_24px_-12px_rgb(0_0_0/0.5)] transition-colors',
        'focus-within:border-foreground/30 focus-within:bg-card/90',
        variant === 'chat' && 'rounded-xl',
      )}
    >
      <textarea
        ref={textareaRef}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
        onInput={handleInput}
        placeholder={placeholder}
        disabled={disabled}
        rows={1}
        autoFocus={autoFocus}
        className={cn(
          'block w-full resize-none border-0 bg-transparent px-4 pb-1 pt-4 text-[15px] leading-6 text-foreground outline-none ring-0',
          'placeholder:text-muted-foreground/70',
          'min-h-[52px] max-h-[200px]',
          'disabled:opacity-50',
        )}
      />

      <div className="flex items-center justify-between gap-1 px-2 pb-2 pt-1">
        <div className="flex items-center gap-0.5">
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                className="text-muted-foreground hover:bg-accent hover:text-foreground"
                aria-label="Attach"
              >
                <Paperclip className="size-4" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>Attach files</TooltipContent>
          </Tooltip>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                className="text-muted-foreground hover:bg-accent hover:text-foreground"
                aria-label="Voice"
              >
                <Mic className="size-4" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>Voice input</TooltipContent>
          </Tooltip>
        </div>

        <div className="flex items-center gap-1">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="h-7 gap-1.5 px-2 text-xs font-normal text-muted-foreground hover:bg-accent hover:text-foreground"
              >
                <ModeIcon className="size-3.5" />
                <span>{mode.label}</span>
                <ChevronDown className="size-3 opacity-60" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-56">
              {SEARCH_MODES.map((m) => {
                const Icon = m.icon;
                return (
                  <DropdownMenuItem
                    key={m.value}
                    onClick={() => setMode(m)}
                    className="flex items-start gap-2 py-2"
                  >
                    <Icon className="mt-0.5 size-4 shrink-0" />
                    <div className="flex flex-col">
                      <span className="text-[13px] font-medium">{m.label}</span>
                      <span className="text-[11px] text-muted-foreground">{m.hint}</span>
                    </div>
                  </DropdownMenuItem>
                );
              })}
            </DropdownMenuContent>
          </DropdownMenu>

          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="h-7 gap-1 px-2 text-xs font-normal text-muted-foreground hover:bg-accent hover:text-foreground"
              >
                <span>{model.label}</span>
                <ChevronDown className="size-3 opacity-60" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-52">
              {MODELS.map((m) => (
                <DropdownMenuItem
                  key={m.value}
                  onClick={() => setModel(m)}
                  className="flex flex-col items-start gap-0.5 py-2"
                >
                  <span className="text-[13px] font-medium">{m.label}</span>
                  <span className="text-[11px] text-muted-foreground">{m.hint}</span>
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>

          <Button
            type="button"
            onClick={handleSubmit}
            disabled={!hasValue || disabled}
            size="icon-sm"
            className={cn(
              'ml-1 size-8 rounded-full transition-all',
              hasValue
                ? 'bg-foreground text-background hover:bg-foreground/90'
                : 'bg-accent text-muted-foreground hover:bg-accent',
            )}
            aria-label="Submit"
          >
            <ArrowUp className="size-4" />
          </Button>
        </div>
      </div>
    </div>
  );
}

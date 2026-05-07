import {
  BarChart3,
  BookOpen,
  Sparkles,
  Star,
  TrendingUp,
} from 'lucide-react';
import { useState } from 'react';
import type { LucideIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

interface Chip {
  icon: LucideIcon;
  label: string;
  query?: string;
}

const CHIPS: Chip[] = [
  { icon: Star, label: 'For you' },
  {
    icon: BarChart3,
    label: 'Analyze a stock',
    query: 'Give me a detailed analysis of Reliance Industries',
  },
  {
    icon: TrendingUp,
    label: 'Market overview',
    query: 'Give me an overview of the Indian stock market today',
  },
  {
    icon: BookOpen,
    label: 'Help me learn',
    query: 'Explain how RSI and MACD indicators work for beginners',
  },
  {
    icon: Sparkles,
    label: 'Build a strategy',
    query: 'Help me build a swing trading strategy for Indian large-caps',
  },
];

interface SuggestionChipsProps {
  onChipClick: (query: string) => void;
}

export function SuggestionChips({ onChipClick }: SuggestionChipsProps) {
  const [activeLabel, setActiveLabel] = useState('For you');

  return (
    <div className="flex flex-wrap items-center justify-center gap-1">
      {CHIPS.map((chip) => {
        const Icon = chip.icon;
        const isActive = chip.label === activeLabel;
        return (
          <Button
            key={chip.label}
            variant="ghost"
            size="sm"
            onClick={() => {
              setActiveLabel(chip.label);
              if (chip.query) onChipClick(chip.query);
            }}
            className={cn(
              'h-8 gap-1.5 rounded-full px-3 text-xs font-medium transition-colors',
              isActive
                ? 'bg-accent text-foreground hover:bg-accent'
                : 'text-muted-foreground hover:bg-accent/60 hover:text-foreground',
            )}
          >
            <Icon className={cn('size-3.5', isActive && 'text-accent-blue')} />
            <span>{chip.label}</span>
          </Button>
        );
      })}
    </div>
  );
}

import { useEffect, useMemo, useState } from 'react';
import { AlertTriangle, Brain, Loader2, RefreshCcw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Popover,
  PopoverContent,
  PopoverHeader,
  PopoverTitle,
  PopoverTrigger,
} from '@/components/ui/popover';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { estimateTokens } from '@/lib/tokenEstimate';
import { cn } from '@/lib/utils';
import { isLocalConversationId, useChatStore } from '@/stores/chatStore';
import * as chatsApi from '@/services/chatsApi';
import type { ContextInfo } from '@/types';

interface ContextIndicatorProps {
  conversationId?: string | null;
  currentInput?: string;
}

const EMPTY_INFO: ContextInfo = {
  system_tokens: 0,
  memory_tokens: 0,
  history_tokens: 0,
  history_compacted: false,
  recent_turns: 0,
  older_turns: 0,
  current_msg_tokens: 0,
  total_tokens: 0,
  budget_tokens: 100_000,
  usage_pct: 0,
};
const CONTEXT_INFO_TIMEOUT_MS = 5_000;

export function ContextIndicator({
  conversationId,
  currentInput = '',
}: ContextIndicatorProps) {
  const storedInfo = useChatStore((s) =>
    conversationId ? s.contextInfo[conversationId] : undefined,
  );
  const setContextInfo = useChatStore((s) => s.setContextInfo);
  const [loading, setLoading] = useState(false);
  const [compacting, setCompacting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!conversationId || isLocalConversationId(conversationId)) return;
    if (storedInfo) return;

    let cancelled = false;
    const controller = new AbortController();
    const timeout = window.setTimeout(() => {
      controller.abort();
    }, CONTEXT_INFO_TIMEOUT_MS);

    setLoading(true);
    setError(null);
    chatsApi
      .getContextInfo(conversationId, { signal: controller.signal })
      .then((info) => {
        if (!cancelled) setContextInfo(conversationId, info);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(
          (err as Error).name === 'AbortError'
            ? 'Context estimate timed out. Check that the backend is running.'
            : (err as Error).message,
        );
      })
      .finally(() => {
        window.clearTimeout(timeout);
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
      window.clearTimeout(timeout);
      controller.abort();
    };
  }, [conversationId, setContextInfo, storedInfo]);

  const info = useMemo(() => {
    const base = storedInfo ?? EMPTY_INFO;
    const currentTokens = estimateTokens(currentInput);
    const total =
      base.total_tokens - base.current_msg_tokens + currentTokens;
    return {
      ...base,
      current_msg_tokens: currentTokens,
      total_tokens: total,
      usage_pct: base.budget_tokens
        ? Number(((total / base.budget_tokens) * 100).toFixed(1))
        : 0,
    };
  }, [currentInput, storedInfo]);

  if (!conversationId || isLocalConversationId(conversationId)) return null;

  const tone = toneFor(info.usage_pct);
  const compactDisabled = compacting || loading;

  const handleCompact = async () => {
    if (!conversationId || compactDisabled) return;
    setCompacting(true);
    setError(null);
    try {
      const next = await chatsApi.compactContext(conversationId);
      setContextInfo(conversationId, next);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setCompacting(false);
    }
  };

  const trigger = (
    <Button
      type="button"
      variant="ghost"
      size="sm"
      className={cn(
        'h-7 gap-1.5 rounded-full px-2 text-xs font-medium',
        tone.className,
      )}
      aria-label="Context usage"
    >
      {error ? (
        <AlertTriangle className="size-3.5" />
      ) : (
        <Brain className="size-3.5" />
      )}
      <span>{Math.max(0, Math.round(info.usage_pct))}%</span>
    </Button>
  );

  return (
    <Popover>
      <Tooltip>
        <TooltipTrigger asChild>
          <PopoverTrigger asChild>{trigger}</PopoverTrigger>
        </TooltipTrigger>
        <TooltipContent className="w-64 bg-popover p-3 text-popover-foreground shadow-md">
          <Breakdown info={info} />
        </TooltipContent>
      </Tooltip>
      <PopoverContent align="center" className="w-80 p-3">
        <PopoverHeader className="mb-3">
          <PopoverTitle className="flex items-center justify-between gap-2 text-sm">
            <span>Context window</span>
            <span className={cn('rounded-full px-2 py-0.5 text-xs', tone.badgeClassName)}>
              {info.usage_pct.toFixed(1)}%
            </span>
          </PopoverTitle>
        </PopoverHeader>
        <Breakdown info={info} />
        <div className="mt-3 flex items-center justify-between gap-2 border-t border-border/70 pt-3">
          <div className="text-[11px] leading-4 text-muted-foreground">
            {loading
              ? 'Estimating saved context...'
              : info.history_compacted
              ? 'Older history is summarized.'
              : `${info.older_turns} older turn${info.older_turns === 1 ? '' : 's'} available.`}
          </div>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={handleCompact}
            disabled={compactDisabled}
            className="h-8 shrink-0 gap-1.5 text-xs"
          >
            {compacting ? (
              <Loader2 className="size-3.5 animate-spin" />
            ) : (
              <RefreshCcw className="size-3.5" />
            )}
            Compact
          </Button>
        </div>
        {error ? (
          <p className="mt-2 text-[11px] leading-4 text-destructive">{error}</p>
        ) : null}
      </PopoverContent>
    </Popover>
  );
}

function Breakdown({ info }: { info: ContextInfo }) {
  const rows = [
    ['System', info.system_tokens],
    ['Memory', info.memory_tokens],
    [`History (${info.recent_turns + info.older_turns} turns)`, info.history_tokens],
    ['Current', info.current_msg_tokens],
  ] as const;

  return (
    <div className="space-y-2 text-xs">
      <div className="h-1.5 overflow-hidden rounded-full bg-muted">
        <div
          className={cn('h-full rounded-full', toneFor(info.usage_pct).barClassName)}
          style={{ width: `${Math.min(100, Math.max(0, info.usage_pct))}%` }}
        />
      </div>
      <div className="space-y-1">
        {rows.map(([label, value]) => (
          <div key={label} className="flex items-center justify-between gap-4">
            <span className="text-muted-foreground">{label}</span>
            <span className="font-mono text-[11px] text-foreground">{formatTokens(value)}</span>
          </div>
        ))}
      </div>
      <div className="flex items-center justify-between gap-4 border-t border-border/70 pt-2">
        <span className="font-medium">Total</span>
        <span className="font-mono text-[11px]">
          {formatTokens(info.total_tokens)} / {formatTokens(info.budget_tokens)}
        </span>
      </div>
    </div>
  );
}

function toneFor(pct: number) {
  if (pct >= 80) {
    return {
      className: 'bg-destructive/10 text-destructive hover:bg-destructive/15',
      badgeClassName: 'bg-destructive/10 text-destructive',
      barClassName: 'bg-destructive',
    };
  }
  if (pct >= 60) {
    return {
      className: 'bg-amber-500/10 text-amber-700 hover:bg-amber-500/15 dark:text-amber-300',
      badgeClassName: 'bg-amber-500/10 text-amber-700 dark:text-amber-300',
      barClassName: 'bg-amber-500',
    };
  }
  return {
    className: 'bg-emerald-500/10 text-emerald-700 hover:bg-emerald-500/15 dark:text-emerald-300',
    badgeClassName: 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300',
    barClassName: 'bg-emerald-500',
  };
}

function formatTokens(value: number): string {
  return new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 }).format(
    Math.max(0, Math.round(value)),
  );
}

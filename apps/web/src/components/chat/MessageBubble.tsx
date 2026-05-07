import { Check, Loader2, AlertTriangle } from 'lucide-react';
import type { Message, ToolEvent } from '@/types';
import { parseMarkdown } from '@/utils/parseMarkdown';
import { ToolCards } from './ToolCards';

interface MessageBubbleProps {
  message: Message;
}

export function MessageBubble({ message }: MessageBubbleProps) {
  if (message.role === 'user') {
    return <UserMessage content={message.content} />;
  }
  return <AssistantMessage message={message} />;
}

function UserMessage({ content }: { content: string }) {
  return (
    <div className="animate-fade-in">
      <h2 className="font-serif text-3xl font-normal leading-snug tracking-tight text-foreground sm:text-[34px]">
        {content}
      </h2>
    </div>
  );
}

function AssistantMessage({ message }: { message: Message }) {
  const { content, sources = [], toolEvents = [], isStreaming, blocked = false } = message;
  const hasContent = content.length > 0;
  const showWaiting = isStreaming && !hasContent && toolEvents.length === 0;

  return (
    <div className="animate-fade-in space-y-4">
      {showWaiting && (
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <Loader2 className="size-3.5 animate-spin text-foreground/70" />
          <span>Routing your question…</span>
        </div>
      )}

      {toolEvents.length > 0 && <ToolEventList events={toolEvents} />}

      {!showWaiting && hasContent && sources.length > 0 && !isStreaming && (
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <span className="flex size-4 items-center justify-center rounded-full bg-accent">
            <Check className="size-2.5 text-foreground/80" />
          </span>
          <span>
            {sources.length} source{sources.length === 1 ? '' : 's'} consulted
          </span>
        </div>
      )}

      {hasContent && (
        <div className="answer-copy">
          {parseMarkdown(content, sources)}
          {isStreaming && (
            <span className="cursor-blink ml-0.5 text-accent-blue">▍</span>
          )}
        </div>
      )}
      {!isStreaming && hasContent && !blocked && toolEvents.length > 0 && (
        <ToolCards events={toolEvents} />
      )}

      {blocked && (
        <div className="flex items-start gap-2 rounded-lg border border-accent-red/40 bg-accent-red/5 px-3 py-2.5">
          <AlertTriangle className="mt-0.5 size-3.5 shrink-0 text-accent-red" />
          <p className="text-[12px] leading-relaxed text-foreground">
            This question crosses the SEBI advice line. Midas refused as
            designed — try asking for facts (price, news, fundamentals) instead.
          </p>
        </div>
      )}
    </div>
  );
}

const TOOL_LABELS: Record<string, string> = {
  memory: 'Memory',
  get_quote: 'Quote',
  get_news: 'News',
  get_company_info: 'Fundamentals',
  remember_fact: 'Memory Save',
};

function ToolEventList({ events }: { events: ToolEvent[] }) {
  return (
    <ul className="flex flex-col gap-1.5">
      {events.map((ev, i) => (
        <ToolEventRow key={`${ev.name}-${i}`} ev={ev} />
      ))}
    </ul>
  );
}

function ToolEventRow({ ev }: { ev: ToolEvent }) {
  const label = TOOL_LABELS[ev.name] ?? ev.name;
  const ticker =
    (ev.summary?.ticker as string | undefined) ??
    (ev.args?.ticker as string | undefined);

  let detail = '';
  if (ev.status === 'done' && ev.summary) {
    if (ev.name === 'memory') {
      const source = ev.summary.source as string | undefined;
      const facts = (ev.summary.facts_count as number | undefined) ?? 0;
      const hits = (ev.summary.hits_count as number | undefined) ?? 0;
      if (source === 'summary+search') detail = `${facts} fact${facts === 1 ? '' : 's'} · semantic recall`;
      else if (source === 'summary') detail = `${facts} fact${facts === 1 ? '' : 's'} cached`;
      else if (source === 'search') detail = `${hits} semantic hit${hits === 1 ? '' : 's'}`;
      else if (ev.summary.reason === 'no_relevant_memory') detail = 'no relevant memory';
    } else if (ev.name === 'remember_fact') {
      detail = ev.summary.stored ? 'saved' : String(ev.summary.error ?? 'save failed');
    } else if (ev.name === 'get_quote') {
      const conf = ev.summary.confidence as string | undefined;
      const ok = (ev.summary.ok_sources as string[] | undefined)?.length ?? 0;
      detail = `${conf ?? '?'} · ${ok} source${ok === 1 ? '' : 's'}`;
    } else if (ev.name === 'get_news') {
      const cnt = (ev.summary.count as number | undefined) ?? 0;
      detail = `${cnt} headline${cnt === 1 ? '' : 's'}`;
    } else if (ev.name === 'get_company_info') {
      const yf = ev.summary.yfinance_ok ? 'yfinance' : '';
      const sc = ev.summary.screener_ok ? 'Screener' : '';
      detail = [yf, sc].filter(Boolean).join(' + ') || '—';
    }
  } else if (ev.status === 'error' && ev.summary) {
    if (ev.name === 'memory') {
      const reason = ev.summary.reason as string | undefined;
      if (reason === 'anonymous') detail = 'sign in required';
      else if (reason === 'disabled') detail = 'disabled';
      else if (reason === 'unconfigured') detail = 'not configured';
      else detail = reason ?? 'unavailable';
    } else if (ev.name === 'remember_fact') {
      detail = String(ev.summary.error ?? 'save failed');
    }
  }

  return (
    <li className="flex items-center gap-2 text-xs">
      {ev.status === 'running' ? (
        <Loader2 className="size-3.5 shrink-0 animate-spin text-muted-foreground" />
      ) : ev.status === 'error' ? (
        <AlertTriangle className="size-3.5 shrink-0 text-accent-red" />
      ) : (
        <span className="flex size-4 shrink-0 items-center justify-center rounded-full bg-accent">
          <Check className="size-2.5 text-foreground/80" />
        </span>
      )}
      <span className="font-medium text-foreground/80">{label}</span>
      {ticker && (
        <span className="rounded-md bg-accent px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-wider text-foreground/80">
          {ticker}
        </span>
      )}
      {detail && <span className="text-muted-foreground">· {detail}</span>}
      {ev.status === 'done' && typeof ev.ms === 'number' && (
        <span className="ml-auto text-[11px] text-muted-foreground">
          {ev.ms < 1000 ? `${ev.ms}ms` : `${(ev.ms / 1000).toFixed(1)}s`}
        </span>
      )}
    </li>
  );
}

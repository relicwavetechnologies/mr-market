/**
 * Data-dense analyst cards rendered under each assistant turn.
 *
 * Each card reads from the matching `tool_result.summary` shape that the
 * backend emits in `app/llm/orchestrator.py::_summarise`. Cards never block
 * — if a tool didn't fire on a turn, its card simply isn't rendered.
 *
 * Visual language (locked in P2-D9):
 *  - Bloomberg-terminal density. No emoji, no "advice" framing.
 *  - Single-row metric grid (label above, value bold below).
 *  - Risk colour comes ONLY from data (e.g. pledge band 'high'),
 *    never from sentiment. Use the `risk-band-*` Tailwind utility classes.
 */

import { useState } from 'react';
import {
  ChevronDown,
  ChevronUp,
  ExternalLink,
  FileText,
  Info,
  TrendingDown,
  TrendingUp,
} from 'lucide-react';
import type {
  DealsSummary,
  HoldingSummary,
  ResearchSummary,
  TechnicalsSummary,
  ToolEvent,
} from '@/types';
import { cn } from '@/lib/utils';

// ---------------------------------------------------------------------------
// Container
// ---------------------------------------------------------------------------

export function ToolCards({ events }: { events: ToolEvent[] }) {
  // Pick the latest done-event per tool name; the model can call the same
  // tool twice on a turn — we want the freshest result.
  const byName = new Map<string, ToolEvent>();
  for (const ev of events) {
    if (ev.status !== 'done') continue;
    byName.set(ev.name, ev);
  }

  const tech = byName.get('get_technicals')?.summary as
    | TechnicalsSummary
    | undefined;
  const holding = byName.get('get_holding')?.summary as
    | HoldingSummary
    | undefined;
  const deals = byName.get('get_deals')?.summary as DealsSummary | undefined;
  const research = byName.get('get_research')?.summary as
    | ResearchSummary
    | undefined;

  if (!tech && !holding && !deals && !research) return null;

  // Render every fired tool — `available: false` becomes an empty-state
  // card rather than a hidden card, so the user can see WHY there's no
  // data ("no technicals computed yet for this ticker") instead of
  // wondering if the tool ran at all.
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
      {tech && <TechnicalsCard data={tech} />}
      {holding && <HoldingCard data={holding} />}
      {deals && <DealsCard data={deals} />}
      {research && <ResearchCard data={research} />}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Shared card chrome
// ---------------------------------------------------------------------------

function CardShell({
  title,
  ticker,
  asOf,
  children,
  className,
}: {
  title: string;
  ticker?: string;
  asOf?: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        'rounded-lg border border-border/70 bg-background/40 p-3',
        className,
      )}
    >
      <div className="mb-2.5 flex items-baseline justify-between">
        <h3 className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
          {title}
        </h3>
        <div className="flex items-center gap-2 text-[10px] tabular-nums text-muted-foreground/80">
          {ticker && (
            <span className="rounded-md bg-accent px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-wider text-foreground/80">
              {ticker}
            </span>
          )}
          {asOf && <span>as of {asOf}</span>}
        </div>
      </div>
      {children}
    </div>
  );
}

function EmptyState({ message }: { message: string }) {
  return (
    <div className="flex items-start gap-2 rounded-md border border-dashed border-border/60 bg-muted/20 px-2.5 py-2.5 text-[12px] text-muted-foreground">
      <Info className="mt-0.5 size-3.5 shrink-0" />
      <span>{message}</span>
    </div>
  );
}

function ExpandToggle({
  open,
  onClick,
  label,
}: {
  open: boolean;
  onClick: () => void;
  label: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="mt-2 flex w-full items-center justify-center gap-1 rounded-md border border-border/40 bg-muted/10 py-1 text-[11px] text-muted-foreground transition-colors hover:bg-muted/30 hover:text-foreground"
    >
      {open ? <ChevronUp className="size-3" /> : <ChevronDown className="size-3" />}
      <span>{label}</span>
    </button>
  );
}

function Metric({
  label,
  value,
  hint,
  tone = 'default',
}: {
  label: string;
  value: React.ReactNode;
  hint?: string;
  tone?: 'default' | 'good' | 'bad' | 'warn';
}) {
  const toneClass =
    tone === 'good'
      ? 'text-teal'
      : tone === 'bad'
        ? 'text-accent-red'
        : tone === 'warn'
          ? 'text-amber-500'
          : 'text-foreground';

  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[10px] uppercase tracking-wider text-muted-foreground/70">
        {label}
      </span>
      <span className={cn('text-sm font-medium tabular-nums', toneClass)}>
        {value ?? '—'}
      </span>
      {hint && <span className="text-[10px] text-muted-foreground">{hint}</span>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Technicals
// ---------------------------------------------------------------------------

function fmtDecimal(v: string | undefined, digits = 2): string {
  if (v === undefined || v === null) return '—';
  const n = Number(v);
  if (Number.isNaN(n)) return v;
  return n.toFixed(digits);
}

export function TechnicalsCard({ data }: { data: TechnicalsSummary }) {
  const [showHistory, setShowHistory] = useState(false);

  if (!data.available) {
    return (
      <CardShell title="Technicals" ticker={data.ticker}>
        <EmptyState message="No technicals computed yet for this ticker. The nightly worker may not have populated the indicators." />
      </CardShell>
    );
  }

  const rsi = fmtDecimal(data.rsi_14, 1);
  const rsiTone =
    data.rsi_zone === 'overbought'
      ? 'warn'
      : data.rsi_zone === 'oversold'
        ? 'good'
        : 'default';
  const macdTone = data.macd_above_signal === true ? 'good' : 'bad';
  const macdHint =
    data.macd_above_signal === true
      ? 'bullish (above signal)'
      : data.macd_above_signal === false
        ? 'bearish (below signal)'
        : undefined;
  const series = data.series ?? [];
  const hasHistory = series.length > 1;

  return (
    <CardShell
      title="Technicals"
      ticker={data.ticker}
      asOf={data.as_of?.slice(0, 10)}
    >
      <div className="grid grid-cols-3 gap-3">
        <Metric
          label="RSI-14"
          value={rsi}
          hint={data.rsi_zone}
          tone={rsiTone}
        />
        <Metric
          label="MACD"
          value={fmtDecimal(data.macd, 2)}
          hint={macdHint}
          tone={macdTone}
        />
        <Metric label="ATR-14" value={fmtDecimal(data.atr_14, 2)} hint="₹" />
        <Metric
          label="Close"
          value={data.close ? `₹${fmtDecimal(data.close, 2)}` : '—'}
        />
        <Metric
          label="vs SMA-50"
          value={data.above_sma50 === true ? 'above' : data.above_sma50 === false ? 'below' : '—'}
          tone={data.above_sma50 ? 'good' : data.above_sma50 === false ? 'bad' : 'default'}
        />
        <Metric
          label="vs SMA-200"
          value={data.above_sma200 === true ? 'above' : data.above_sma200 === false ? 'below' : '—'}
          tone={data.above_sma200 ? 'good' : data.above_sma200 === false ? 'bad' : 'default'}
        />
      </div>

      {hasHistory && (
        <>
          <ExpandToggle
            open={showHistory}
            onClick={() => setShowHistory((v) => !v)}
            label={showHistory ? 'Hide history' : `History (${series.length} bars)`}
          />
          {showHistory && (
            <table className="mt-2 w-full text-[11px] tabular-nums">
              <thead>
                <tr className="text-muted-foreground/70">
                  <th className="text-left font-normal">Date</th>
                  <th className="text-right font-normal">Close</th>
                  <th className="text-right font-normal">RSI</th>
                </tr>
              </thead>
              <tbody>
                {series.map((s, i) => (
                  <tr
                    key={i}
                    className="border-t border-border/30 text-foreground/80"
                  >
                    <td className="py-1 text-left">
                      {s.ts ? s.ts.slice(0, 10) : '—'}
                    </td>
                    <td className="py-1 text-right">
                      {s.close ? `₹${fmtDecimal(s.close, 2)}` : '—'}
                    </td>
                    <td className="py-1 text-right">
                      {s.rsi_14 ? fmtDecimal(s.rsi_14, 1) : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </CardShell>
  );
}

// ---------------------------------------------------------------------------
// Holding (with pledge risk-band callout)
// ---------------------------------------------------------------------------

const PLEDGE_BAND_TONE: Record<
  NonNullable<HoldingSummary['pledge_risk_band']>,
  string
> = {
  low: 'border-teal/40 bg-teal/5 text-teal',
  moderate: 'border-amber-500/40 bg-amber-500/5 text-amber-500',
  elevated: 'border-orange-500/40 bg-orange-500/5 text-orange-500',
  high: 'border-accent-red/40 bg-accent-red/5 text-accent-red',
  unknown: 'border-border/60 bg-muted/30 text-muted-foreground',
};

const PLEDGE_BAND_LABEL: Record<
  NonNullable<HoldingSummary['pledge_risk_band']>,
  string
> = {
  low: 'Low pledge',
  moderate: 'Moderate pledge',
  elevated: 'Elevated pledge',
  high: 'High pledge',
  unknown: 'Pledge data unavailable',
};

export function HoldingCard({ data }: { data: HoldingSummary }) {
  const [showHistory, setShowHistory] = useState(false);

  if (!data.available) {
    return (
      <CardShell title="Shareholding" ticker={data.ticker}>
        <EmptyState message="No shareholding rows on file. The NSE quarterly scrape may not have run for this ticker yet." />
      </CardShell>
    );
  }

  const band = data.pledge_risk_band ?? 'unknown';
  const showPledge = data.pledged_pct !== undefined && data.pledged_pct !== null;
  const series = data.series ?? [];
  const hasHistory = series.length > 1;

  return (
    <CardShell title="Shareholding" ticker={data.ticker} asOf={data.latest_quarter}>
      <div className="grid grid-cols-3 gap-3">
        <Metric label="Promoter" value={`${fmtDecimal(data.promoter_pct, 2)}%`} />
        <Metric label="Public" value={`${fmtDecimal(data.public_pct, 2)}%`} />
        <Metric
          label="Emp. Trust"
          value={`${fmtDecimal(data.employee_trust_pct, 2)}%`}
        />
      </div>

      {showPledge && (
        <div
          className={cn(
            'mt-3 flex items-center justify-between gap-2 rounded-md border px-2.5 py-1.5',
            PLEDGE_BAND_TONE[band],
          )}
        >
          <div className="flex flex-col">
            <span className="text-[10px] uppercase tracking-wider opacity-80">
              {PLEDGE_BAND_LABEL[band]}
            </span>
            <span className="text-sm font-medium tabular-nums">
              {fmtDecimal(data.pledged_pct, 2)}% of promoter holding pledged
            </span>
          </div>
          {data.xbrl_url && (
            <a
              href={data.xbrl_url}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1 text-[11px] underline-offset-2 hover:underline"
              title="Open NSE XBRL filing in a new tab"
            >
              XBRL
              <ExternalLink className="size-3" />
            </a>
          )}
        </div>
      )}

      {hasHistory && (
        <>
          <ExpandToggle
            open={showHistory}
            onClick={() => setShowHistory((v) => !v)}
            label={showHistory ? 'Hide history' : `History (${series.length} quarters)`}
          />
          {showHistory && (
            <table className="mt-2 w-full text-[11px] tabular-nums">
              <thead>
                <tr className="text-muted-foreground/70">
                  <th className="text-left font-normal">Quarter</th>
                  <th className="text-right font-normal">Promoter</th>
                  <th className="text-right font-normal">Public</th>
                </tr>
              </thead>
              <tbody>
                {series.map((s, i) => (
                  <tr
                    key={i}
                    className="border-t border-border/30 text-foreground/80"
                  >
                    <td className="py-1 text-left">{s.quarter_label ?? '—'}</td>
                    <td className="py-1 text-right">
                      {s.promoter_pct ? `${fmtDecimal(s.promoter_pct, 2)}%` : '—'}
                    </td>
                    <td className="py-1 text-right">
                      {s.public_pct ? `${fmtDecimal(s.public_pct, 2)}%` : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </CardShell>
  );
}

// ---------------------------------------------------------------------------
// Deals (bulk + block)
// ---------------------------------------------------------------------------

export function DealsCard({ data }: { data: DealsSummary }) {
  if (!data.available) {
    return (
      <CardShell title={`Deals — ${data.kind ?? 'any'}`} ticker={data.ticker}>
        <EmptyState message="No bulk or block deals reported by NSE for this ticker in the lookback window." />
      </CardShell>
    );
  }

  const net = data.net_qty ?? 0;
  const netTone = net > 0 ? 'good' : net < 0 ? 'bad' : 'default';
  const netHint = net > 0 ? 'net BUY' : net < 0 ? 'net SELL' : 'flat';
  const Icon = net >= 0 ? TrendingUp : TrendingDown;

  return (
    <CardShell
      title={`Deals — ${data.kind ?? 'any'}`}
      ticker={data.ticker}
    >
      <div className="grid grid-cols-3 gap-3">
        <Metric label="Total" value={data.n_deals ?? '—'} />
        <Metric label="Buys" value={data.n_buys ?? '—'} tone="good" />
        <Metric label="Sells" value={data.n_sells ?? '—'} tone="bad" />
      </div>
      <div className="mt-3 flex items-center justify-between rounded-md border border-border/60 bg-muted/30 px-2.5 py-1.5">
        <div className="flex flex-col">
          <span className="text-[10px] uppercase tracking-wider text-muted-foreground/70">
            Net qty
          </span>
          <span
            className={cn(
              'text-sm font-medium tabular-nums',
              netTone === 'good' && 'text-teal',
              netTone === 'bad' && 'text-accent-red',
            )}
          >
            {net.toLocaleString('en-IN')}{' '}
            <span className="text-[11px] font-normal text-muted-foreground">
              · {netHint}
            </span>
          </span>
        </div>
        <Icon
          className={cn(
            'size-4',
            netTone === 'good' && 'text-teal',
            netTone === 'bad' && 'text-accent-red',
            netTone === 'default' && 'text-muted-foreground',
          )}
        />
      </div>
    </CardShell>
  );
}

// ---------------------------------------------------------------------------
// Research (RAG hits)
// ---------------------------------------------------------------------------

export function ResearchCard({ data }: { data: ResearchSummary }) {
  if (!data.available) {
    return (
      <CardShell title="Research" ticker={data.ticker}>
        <EmptyState message="No annual report or research document indexed for this ticker yet. Ask an operator to run scripts.ingest_research." />
      </CardShell>
    );
  }

  const hits = data.top_hits ?? [];
  return (
    <CardShell title="Research" ticker={data.ticker}>
      <div className="mb-2 flex items-center gap-3 text-[11px] text-muted-foreground">
        <span>
          {data.n_hits ?? 0} hit{data.n_hits === 1 ? '' : 's'}
        </span>
        {typeof data.top_score === 'number' && (
          <span className="tabular-nums">top score {data.top_score.toFixed(3)}</span>
        )}
      </div>
      {hits.length > 0 ? (
        <ul className="flex flex-col gap-1.5">
          {hits.map((h, i) => (
            <li
              key={i}
              className="flex items-start gap-2 rounded-md border border-border/60 bg-muted/20 px-2 py-1.5"
            >
              <FileText className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" />
              <div className="min-w-0 flex-1">
                <p className="truncate text-[12px] font-medium text-foreground">
                  {h.document_title ?? 'Untitled'}{' '}
                  {h.document_fy && (
                    <span className="text-muted-foreground">· {h.document_fy}</span>
                  )}
                </p>
                <p className="text-[11px] tabular-nums text-muted-foreground">
                  page {h.page ?? '—'}
                  {typeof h.score === 'number' && ` · score ${h.score.toFixed(3)}`}
                </p>
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-[11px] text-muted-foreground">No chunks returned.</p>
      )}
    </CardShell>
  );
}

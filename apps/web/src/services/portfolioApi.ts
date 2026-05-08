import { apiFetch, parseJsonOrThrow } from './apiClient';

export interface PortfolioImportResult {
  ok?: boolean;
  portfolio_id: number;
  n_positions: number;
  total_cost_inr: string;
  format: 'csv' | 'cdsl_paste' | 'json' | string;
  skipped_rows?: string[];
  unknown_tickers?: string[];
  error?: string;
}

export interface PortfolioHoldingInput {
  ticker: string;
  quantity: number;
  avg_price?: string;
}

export interface PortfolioImportOptions {
  /** Free-form CSV / Zerodha-CDSL-paste blob; server auto-detects. */
  rawText?: string;
  /** Pre-parsed positions, e.g. from a UI form. */
  holdings?: PortfolioHoldingInput[];
  /** Override server auto-detection. */
  format?: 'csv' | 'cdsl_paste';
  /** Optional friendly label. */
  name?: string;
}

/**
 * POST /portfolio/import — auth-gated portfolio import.
 *
 * Two paths:
 *  - `rawText`: paste a CSV file or a Zerodha holdings-page block; the
 *    server parses it (header-driven CSV, or Zerodha tab/space-delimited).
 *  - `holdings`: pre-parsed array of {ticker, quantity, avg_price}.
 *
 * Out-of-NIFTY-100 tickers are dropped and surfaced in `unknown_tickers`.
 * Repeated rows for the same ticker are collapsed with a weighted-average
 * cost. Returns the new `portfolio_id` for downstream `/portfolio/{id}/
 * diagnostics` calls (or `analyse_portfolio` LLM tool).
 */
export async function importPortfolio(
  opts: PortfolioImportOptions,
): Promise<PortfolioImportResult> {
  const body: Record<string, unknown> = {};
  if (opts.rawText && opts.rawText.trim()) body.raw_text = opts.rawText;
  if (opts.holdings && opts.holdings.length > 0) body.holdings = opts.holdings;
  if (opts.format) body.format = opts.format;
  if (opts.name) body.name = opts.name;

  const res = await apiFetch('/portfolio/import', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  });
  return parseJsonOrThrow<PortfolioImportResult>(res, 'import portfolio');
}

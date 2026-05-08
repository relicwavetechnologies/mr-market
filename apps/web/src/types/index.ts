export interface Source {
  title: string;
  url?: string;
  domain?: string;
}

export type ToolName =
  | 'get_quote'
  | 'get_news'
  | 'get_company_info'
  | 'get_technicals'
  | 'get_levels'
  | 'get_holding'
  | 'get_deals'
  | 'get_research'
  | 'run_screener'
  | 'analyse_portfolio'
  | 'propose_ideas'
  | 'backtest_screener'
  | 'add_to_watchlist';

export interface ToolEvent {
  name: ToolName | string;
  status: 'running' | 'done' | 'error';
  args?: Record<string, unknown>;
  summary?: Record<string, unknown>;
  ms?: number;
}

export interface ContextInfo {
  system_tokens: number;
  memory_tokens: number;
  history_tokens: number;
  history_compacted: boolean;
  recent_turns: number;
  older_turns: number;
  current_msg_tokens: number;
  total_tokens: number;
  budget_tokens: number;
  usage_pct: number;
}

// ----- Tool-summary shapes (mirror app/llm/orchestrator.py::_summarise) -----
// All numeric fields are stringified (Decimal serialization) on the wire;
// renderers should call `Number(x)` or display verbatim.

export interface TechnicalsSeriesPoint {
  ts?: string;
  close?: string;
  rsi_14?: string;
}

export interface TechnicalsSummary {
  ticker?: string;
  available?: boolean;
  as_of?: string;
  close?: string;
  rsi_14?: string;
  rsi_zone?: 'overbought' | 'oversold' | 'neutral';
  macd?: string;
  macd_signal?: string;
  macd_above_signal?: boolean;
  sma_50?: string;
  sma_200?: string;
  above_sma50?: boolean;
  above_sma200?: boolean;
  atr_14?: string;
  series?: TechnicalsSeriesPoint[];
}

export interface HoldingSeriesPoint {
  quarter_label?: string;
  promoter_pct?: string;
  public_pct?: string;
}

export interface HoldingSummary {
  ticker?: string;
  available?: boolean;
  latest_quarter?: string;
  promoter_pct?: string;
  public_pct?: string;
  employee_trust_pct?: string;
  pledged_pct?: string;
  pledge_risk_band?: 'low' | 'moderate' | 'elevated' | 'high' | 'unknown';
  xbrl_url?: string | null;
  n_quarters?: number;
  series?: HoldingSeriesPoint[];
}

export interface DealsSummary {
  ticker?: string;
  available?: boolean;
  kind?: 'bulk' | 'block' | 'any';
  n_deals?: number;
  n_buys?: number;
  n_sells?: number;
  net_qty?: number;
}

export interface ResearchHit {
  document_title?: string;
  document_fy?: string;
  page?: number;
  score?: number;
}

export interface ResearchSummary {
  ticker?: string;
  available?: boolean;
  n_hits?: number;
  top_score?: number;
  top_hits?: ResearchHit[];
  documents?: [string | null, string | null][];
}

// ----- Phase-3 tool-summary shapes -----------------------------------------

export interface ScreenerTicker {
  symbol?: string;
  score?: number;
}

export interface ScreenerSummary {
  available?: boolean;
  screener_name?: string;
  expr?: string;
  n_matches?: number;
  universe_size?: number;
  exec_ms?: number;
  top_tickers?: string[];
  error?: string;
}

export interface PortfolioConcentration {
  top_5_pct?: string;   // already a percentage, as a Decimal-string ("100.0")
  herfindahl?: string;  // 0..1, as a Decimal-string ("0.4412")
}

export interface PortfolioSectorEntry {
  sector: string;
  pct: string;          // already a percentage, as a Decimal-string ("38.5")
}

export interface PortfolioPickerEntry {
  id: number;
  name: string;
  source: string | null;
  created_at: string | null;
}

export interface PortfolioSummary {
  // Standard diagnostics shape — every numeric is a Decimal-string.
  available?: boolean;
  portfolio_id?: number;
  as_of?: string;
  n_positions?: number;
  total_value_inr?: string;
  concentration?: PortfolioConcentration;
  sector_pct?: PortfolioSectorEntry[];
  beta_blend?: string;     // value-weighted; "1.04"
  div_yield?: string;      // already %; "1.85"
  drawdown_1y?: string;    // already %; "-7.4"
  diagnostics_notes?: {
    missing_beta_count?: number;
    n_priced?: number;
  };

  // Picker / empty-state variants (analyse_portfolio without explicit id).
  needs_pick?: boolean;
  needs_import?: boolean;
  portfolios?: PortfolioPickerEntry[];
  message?: string;
  error?: string;
}

export interface TradeIdea {
  ticker?: string;
  thesis?: string;
  entry?: number;
  sl?: number;
  target?: number;
  rr_ratio?: number;
  score?: number;
}

export interface TradeIdeaSummary {
  available?: boolean;
  risk_profile?: string;
  theme?: string;
  n_ideas?: number;
  ideas?: TradeIdea[];
  error?: string;
}

export interface BacktestSummary {
  available?: boolean;
  screener_name?: string;
  period_days?: number;
  hit_rate?: number;
  mean_return?: number;
  worst_drawdown?: number;
  n_signals?: number;
  error?: string;
}

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  sources?: Source[];
  toolEvents?: ToolEvent[];
  intent?: string | null;
  ticker?: string | null;
  blocked?: boolean;
  timestamp: Date;
  isStreaming?: boolean;
  completionTime?: number;
}

export interface Conversation {
  id: string;
  title: string;
  lastMessage: string;
  createdAt?: Date;
  updatedAt: Date;
}

export interface User {
  id: string;
  name: string;
  email: string;
  avatar?: string;
  riskProfile?: 'conservative' | 'moderate' | 'aggressive';
}

export interface AuthStatus {
  configured: boolean;
  source: 'codex_oauth' | 'codex_cli' | 'env' | 'redis' | 'none' | string;
  model_work: string;
  model_router: string;
  using_fallback?: boolean;
  fallback_reason?: string | null;
  codex_auth_path?: string | null;
  expires_at?: number | null;
  hint?: string | null;
}

export interface CodexInitiateResponse {
  auth_url: string;
  state: string;
  redirect_uri: string;
}

export type ChatStreamEvent =
  | {
      type: 'auth';
      source: string;
      model?: string;
      using_fallback?: boolean;
      message?: string | null;
    }
  | { type: 'conversation'; conversation_id: string }
  | { type: 'status'; message: string }
  | {
      type: 'memory_status';
      status: 'used' | 'miss' | 'unavailable';
      source: 'summary' | 'search' | 'summary+search' | 'none';
      reason: string | null;
      summary_version?: number | null;
      facts_count?: number;
      hits_count?: number;
    }
  | ({ type: 'context_info' } & ContextInfo)
  | { type: 'intent'; intent: string | null; ticker: string | null }
  | { type: 'tool_call'; name: string; args: Record<string, unknown> }
  | {
      type: 'tool_result';
      name: string;
      ms: number;
      summary: Record<string, unknown>;
    }
  | { type: 'delta'; text: string }
  | {
      type: 'done';
      message: string;
      tool_results: Record<string, unknown>;
      blocked: boolean;
    }
  | { type: 'error'; message: string };

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
  | 'get_research';

export interface ToolEvent {
  name: ToolName | string;
  status: 'running' | 'done' | 'error';
  args?: Record<string, unknown>;
  summary?: Record<string, unknown>;
  ms?: number;
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
  | {
      type: 'memory_status';
      status: 'used' | 'miss' | 'unavailable';
      source: 'summary' | 'search' | 'summary+search' | 'none';
      reason: string | null;
      summary_version?: number | null;
      facts_count?: number;
      hits_count?: number;
    }
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

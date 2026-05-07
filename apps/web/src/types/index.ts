export interface Source {
  title: string;
  url?: string;
  domain?: string;
}

export interface ToolEvent {
  name: 'get_quote' | 'get_news' | 'get_company_info' | string;
  status: 'running' | 'done' | 'error';
  args?: Record<string, unknown>;
  summary?: Record<string, unknown>;
  ms?: number;
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
  source: 'codex_cli' | 'env' | 'redis' | 'none' | string;
  model_work: string;
  model_router: string;
  codex_auth_path?: string | null;
  hint?: string | null;
}

export type ChatStreamEvent =
  | { type: 'auth'; source: string }
  | { type: 'conversation'; conversation_id: string }
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

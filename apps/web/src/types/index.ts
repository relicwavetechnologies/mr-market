export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: Source[];
  timestamp: Date;
  isStreaming?: boolean;
  guardrail?: {
    overridden: boolean;
    disclaimer_injected: boolean;
    blocklist_hits: { rule_id: string; category: string; matched: string }[];
    claim_mismatches: {
      raw: string;
      value: string;
      unit: string | null;
      closest: string | null;
      delta_pct: string | null;
    }[];
    router_short_circuit?: boolean;
  };
}

export interface Source {
  title: string;
  url?: string;
  snippet?: string;
}

export interface Conversation {
  id: string;
  title: string;
  messages: Message[];
  createdAt: Date;
  updatedAt: Date;
}

export interface User {
  id: string;
  email: string;
  name: string;
  riskProfile?: "conservative" | "moderate" | "aggressive";
  avatarUrl?: string;
}

export interface SuggestionChip {
  icon: string;
  label: string;
  query: string;
}

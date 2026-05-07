export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  sources?: Source[];
  timestamp: Date;
  isStreaming?: boolean;
  completionTime?: number;
}

export interface Source {
  title: string;
  url: string;
  domain: string;
}

export interface Conversation {
  id: string;
  title: string;
  lastMessage: string;
  updatedAt: Date;
}

export interface User {
  id: string;
  name: string;
  email: string;
  avatar?: string;
  riskProfile?: 'conservative' | 'moderate' | 'aggressive';
}

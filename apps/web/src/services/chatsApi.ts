import { apiFetch, parseJsonOrThrow } from './apiClient';
import type { ContextInfo, Conversation, Message } from '@/types';

interface ApiConversation {
  id: string;
  title: string;
  last_message: string;
  created_at: string;
  updated_at: string;
}

interface ApiMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  sources?: Message['sources'];
  tool_events?: Message['toolEvents'];
  intent?: string | null;
  ticker?: string | null;
  blocked?: boolean;
  completion_time_ms?: number | null;
  created_at: string;
}

interface ApiConversationDetail extends ApiConversation {
  messages: ApiMessage[];
}

export interface ConversationDetail {
  conversation: Conversation;
  messages: Message[];
}

export async function listChats(): Promise<Conversation[]> {
  const res = await apiFetch('/api/chats');
  const payload = await parseJsonOrThrow<ApiConversation[]>(res, 'Load chats');
  return payload.map(normalizeConversation);
}

export async function createChat(title = 'New Chat'): Promise<ConversationDetail> {
  const res = await apiFetch('/api/chats', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title }),
  });
  return normalizeDetail(await parseJsonOrThrow<ApiConversationDetail>(res, 'Create chat'));
}

export async function getChat(id: string): Promise<ConversationDetail> {
  const res = await apiFetch(`/api/chats/${id}`);
  return normalizeDetail(await parseJsonOrThrow<ApiConversationDetail>(res, 'Load chat'));
}

export async function getContextInfo(
  id: string,
  init: Pick<RequestInit, 'signal'> = {},
): Promise<ContextInfo> {
  const res = await apiFetch(`/api/chats/${id}/context-info`, init);
  return parseJsonOrThrow<ContextInfo>(res, 'Load context info');
}

export async function compactContext(id: string): Promise<ContextInfo> {
  const res = await apiFetch(`/api/chats/${id}/compact`, { method: 'POST' });
  return parseJsonOrThrow<ContextInfo>(res, 'Compact context');
}

export async function renameChat(id: string, title: string): Promise<Conversation> {
  const res = await apiFetch(`/api/chats/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title }),
  });
  return normalizeConversation(await parseJsonOrThrow<ApiConversation>(res, 'Rename chat'));
}

export async function deleteChat(id: string): Promise<void> {
  const res = await apiFetch(`/api/chats/${id}`, { method: 'DELETE' });
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`Delete chat failed (${res.status}): ${text || res.statusText}`);
  }
}

function normalizeDetail(payload: ApiConversationDetail): ConversationDetail {
  return {
    conversation: normalizeConversation(payload),
    messages: payload.messages.map(normalizeMessage),
  };
}

function normalizeConversation(payload: ApiConversation): Conversation {
  return {
    id: payload.id,
    title: payload.title,
    lastMessage: payload.last_message,
    createdAt: new Date(payload.created_at),
    updatedAt: new Date(payload.updated_at),
  };
}

function normalizeMessage(payload: ApiMessage): Message {
  return {
    id: payload.id,
    role: payload.role,
    content: payload.content,
    sources: payload.sources ?? [],
    toolEvents: payload.tool_events ?? [],
    intent: payload.intent,
    ticker: payload.ticker,
    blocked: payload.blocked,
    timestamp: new Date(payload.created_at),
    completionTime:
      typeof payload.completion_time_ms === 'number'
        ? payload.completion_time_ms / 1000
        : undefined,
  };
}

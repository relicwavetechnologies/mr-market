import { create } from 'zustand';
import * as chatsApi from '@/services/chatsApi';
import type { ContextInfo, Conversation, Message } from '@/types';

const LOCAL_ID_PREFIX = 'local-';

interface ChatState {
  conversations: Conversation[];
  activeConversationId: string | null;
  messages: Record<string, Message[]>;
  contextInfo: Record<string, ContextInfo>;
  isGenerating: boolean;

  createConversation: (title?: string) => string;
  hydrateFromServer: () => Promise<void>;
  fetchConversation: (id: string) => Promise<void>;
  replaceConversationId: (oldId: string, newId: string) => void;
  sendMessage: (conversationId: string, message: Message) => void;
  updateMessageContent: (conversationId: string, messageId: string, content: string) => void;
  updateMessageStreaming: (conversationId: string, messageId: string, isStreaming: boolean) => void;
  updateMessageSources: (conversationId: string, messageId: string, sources: Message['sources']) => void;
  updateMessageCompletionTime: (conversationId: string, messageId: string, time: number) => void;
  patchMessage: (conversationId: string, messageId: string, patch: Partial<Message>) => void;
  setContextInfo: (conversationId: string, info: ContextInfo) => void;
  setActiveConversation: (id: string | null) => void;
  setIsGenerating: (generating: boolean) => void;
  deleteConversation: (id: string) => Promise<void>;
  clearAll: () => void;
}

export function isLocalConversationId(id: string | null | undefined): boolean {
  return Boolean(id?.startsWith(LOCAL_ID_PREFIX));
}

export const useChatStore = create<ChatState>((set, get) => ({
  conversations: [],
  activeConversationId: null,
  messages: {},
  contextInfo: {},
  isGenerating: false,

  createConversation: (title?: string) => {
    const id = `${LOCAL_ID_PREFIX}${crypto.randomUUID()}`;
    const conversation: Conversation = {
      id,
      title: title ?? 'New Chat',
      lastMessage: '',
      createdAt: new Date(),
      updatedAt: new Date(),
    };
    set((state) => ({
      conversations: [conversation, ...state.conversations],
      activeConversationId: id,
      messages: { ...state.messages, [id]: [] },
    }));
    return id;
  },

  hydrateFromServer: async () => {
    const conversations = await chatsApi.listChats();
    set({
      conversations,
      messages: {},
      contextInfo: {},
      activeConversationId: null,
    });
  },

  fetchConversation: async (id: string) => {
    if (isLocalConversationId(id)) return;
    const detail = await chatsApi.getChat(id);
    set((state) => ({
      conversations: upsertConversation(state.conversations, detail.conversation),
      messages: {
        ...state.messages,
        [id]: detail.messages,
      },
    }));
  },

  replaceConversationId: (oldId: string, newId: string) => {
    if (oldId === newId) return;
    set((state) => {
      const oldMessages = state.messages[oldId] ?? [];
      const messages = { ...state.messages };
      delete messages[oldId];
      messages[newId] = oldMessages;
      const contextInfo = { ...state.contextInfo };
      if (contextInfo[oldId]) {
        contextInfo[newId] = contextInfo[oldId];
        delete contextInfo[oldId];
      }

      const conversations = state.conversations.map((conversation) =>
        conversation.id === oldId
          ? { ...conversation, id: newId, updatedAt: new Date() }
          : conversation,
      );

      return {
        conversations,
        messages,
        contextInfo,
        activeConversationId:
          state.activeConversationId === oldId ? newId : state.activeConversationId,
      };
    });
  },

  sendMessage: (conversationId: string, message: Message) => {
    set((state) => {
      const existing = state.messages[conversationId] ?? [];
      const titleUpdate =
        message.role === 'user' && existing.length === 0
          ? message.content.length > 50
            ? `${message.content.slice(0, 50)}...`
            : message.content
          : undefined;

      return {
        messages: {
          ...state.messages,
          [conversationId]: [...existing, message],
        },
        conversations: state.conversations.map((c) =>
          c.id === conversationId
            ? {
                ...c,
                lastMessage: message.content.slice(0, 100),
                updatedAt: new Date(),
                ...(titleUpdate ? { title: titleUpdate } : {}),
              }
            : c,
        ),
      };
    });
  },

  updateMessageContent: (conversationId: string, messageId: string, content: string) => {
    set((state) => ({
      messages: {
        ...state.messages,
        [conversationId]: (state.messages[conversationId] ?? []).map((m) =>
          m.id === messageId ? { ...m, content } : m,
        ),
      },
    }));
  },

  updateMessageStreaming: (conversationId: string, messageId: string, isStreaming: boolean) => {
    set((state) => ({
      messages: {
        ...state.messages,
        [conversationId]: (state.messages[conversationId] ?? []).map((m) =>
          m.id === messageId ? { ...m, isStreaming } : m,
        ),
      },
    }));
  },

  updateMessageSources: (conversationId: string, messageId: string, sources: Message['sources']) => {
    set((state) => ({
      messages: {
        ...state.messages,
        [conversationId]: (state.messages[conversationId] ?? []).map((m) =>
          m.id === messageId ? { ...m, sources } : m,
        ),
      },
    }));
  },

  updateMessageCompletionTime: (conversationId: string, messageId: string, time: number) => {
    set((state) => ({
      messages: {
        ...state.messages,
        [conversationId]: (state.messages[conversationId] ?? []).map((m) =>
          m.id === messageId ? { ...m, completionTime: time } : m,
        ),
      },
    }));
  },

  patchMessage: (conversationId: string, messageId: string, patch: Partial<Message>) => {
    set((state) => ({
      messages: {
        ...state.messages,
        [conversationId]: (state.messages[conversationId] ?? []).map((m) =>
          m.id === messageId ? { ...m, ...patch } : m,
        ),
      },
    }));
  },

  setContextInfo: (conversationId: string, info: ContextInfo) => {
    set((state) => ({
      contextInfo: {
        ...state.contextInfo,
        [conversationId]: info,
      },
    }));
  },

  setActiveConversation: (id: string | null) => {
    set({ activeConversationId: id });
  },

  setIsGenerating: (generating: boolean) => {
    set({ isGenerating: generating });
  },

  deleteConversation: async (id: string) => {
    if (!isLocalConversationId(id)) await chatsApi.deleteChat(id);
    set((state) => {
      const messages = { ...state.messages };
      const contextInfo = { ...state.contextInfo };
      delete messages[id];
      delete contextInfo[id];
      return {
        conversations: state.conversations.filter((c) => c.id !== id),
        messages,
        contextInfo,
        activeConversationId: state.activeConversationId === id ? null : state.activeConversationId,
      };
    });
  },

  clearAll: () => {
    get().setIsGenerating(false);
    set({
      conversations: [],
      activeConversationId: null,
      messages: {},
      contextInfo: {},
      isGenerating: false,
    });
  },
}));

function upsertConversation(conversations: Conversation[], next: Conversation): Conversation[] {
  const existing = conversations.filter((c) => c.id !== next.id);
  return [next, ...existing].sort((a, b) => b.updatedAt.getTime() - a.updatedAt.getTime());
}

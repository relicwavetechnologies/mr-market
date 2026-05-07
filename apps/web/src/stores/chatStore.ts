import { create } from 'zustand';
import type { Conversation, Message } from '@/types';

interface ChatState {
  conversations: Conversation[];
  activeConversationId: string | null;
  messages: Record<string, Message[]>;
  isGenerating: boolean;

  createConversation: (title?: string) => string;
  sendMessage: (conversationId: string, message: Message) => void;
  updateMessageContent: (conversationId: string, messageId: string, content: string) => void;
  updateMessageStreaming: (conversationId: string, messageId: string, isStreaming: boolean) => void;
  updateMessageSources: (conversationId: string, messageId: string, sources: Message['sources']) => void;
  updateMessageCompletionTime: (conversationId: string, messageId: string, time: number) => void;
  patchMessage: (conversationId: string, messageId: string, patch: Partial<Message>) => void;
  setActiveConversation: (id: string | null) => void;
  setIsGenerating: (generating: boolean) => void;
  deleteConversation: (id: string) => void;
}

export const useChatStore = create<ChatState>((set) => ({
  conversations: [],
  activeConversationId: null,
  messages: {},
  isGenerating: false,

  createConversation: (title?: string) => {
    const id = crypto.randomUUID();
    const conversation: Conversation = {
      id,
      title: title ?? 'New Chat',
      lastMessage: '',
      updatedAt: new Date(),
    };
    set((state) => ({
      conversations: [conversation, ...state.conversations],
      activeConversationId: id,
      messages: { ...state.messages, [id]: [] },
    }));
    return id;
  },

  sendMessage: (conversationId: string, message: Message) => {
    set((state) => {
      const existing = state.messages[conversationId] ?? [];
      const titleUpdate =
        message.role === 'user' && existing.length === 0
          ? message.content.length > 50
            ? message.content.slice(0, 50) + '...'
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
            : c
        ),
      };
    });
  },

  updateMessageContent: (conversationId: string, messageId: string, content: string) => {
    set((state) => ({
      messages: {
        ...state.messages,
        [conversationId]: (state.messages[conversationId] ?? []).map((m) =>
          m.id === messageId ? { ...m, content } : m
        ),
      },
    }));
  },

  updateMessageStreaming: (conversationId: string, messageId: string, isStreaming: boolean) => {
    set((state) => ({
      messages: {
        ...state.messages,
        [conversationId]: (state.messages[conversationId] ?? []).map((m) =>
          m.id === messageId ? { ...m, isStreaming } : m
        ),
      },
    }));
  },

  updateMessageSources: (conversationId: string, messageId: string, sources: Message['sources']) => {
    set((state) => ({
      messages: {
        ...state.messages,
        [conversationId]: (state.messages[conversationId] ?? []).map((m) =>
          m.id === messageId ? { ...m, sources } : m
        ),
      },
    }));
  },

  updateMessageCompletionTime: (conversationId: string, messageId: string, time: number) => {
    set((state) => ({
      messages: {
        ...state.messages,
        [conversationId]: (state.messages[conversationId] ?? []).map((m) =>
          m.id === messageId ? { ...m, completionTime: time } : m
        ),
      },
    }));
  },

  patchMessage: (conversationId: string, messageId: string, patch: Partial<Message>) => {
    set((state) => ({
      messages: {
        ...state.messages,
        [conversationId]: (state.messages[conversationId] ?? []).map((m) =>
          m.id === messageId ? { ...m, ...patch } : m
        ),
      },
    }));
  },

  setActiveConversation: (id: string | null) => {
    set({ activeConversationId: id });
  },

  setIsGenerating: (generating: boolean) => {
    set({ isGenerating: generating });
  },

  deleteConversation: (id: string) => {
    set((state) => {
      const newMessages = { ...state.messages };
      delete newMessages[id];
      return {
        conversations: state.conversations.filter((c) => c.id !== id),
        messages: newMessages,
        activeConversationId:
          state.activeConversationId === id ? null : state.activeConversationId,
      };
    });
  },
}));

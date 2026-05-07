import { create } from "zustand";
import type { Conversation, Message } from "@/types";

interface ChatState {
  conversations: Conversation[];
  activeConversationId: string | null;
  isLoading: boolean;

  createConversation: (firstMessage?: string) => string;
  addMessage: (conversationId: string, message: Message) => void;
  updateMessage: (
    conversationId: string,
    messageId: string,
    content: string,
  ) => void;
  setActiveConversation: (id: string | null) => void;
  getActiveConversation: () => Conversation | undefined;
  setLoading: (loading: boolean) => void;
}

export const useChatStore = create<ChatState>((set, get) => ({
  conversations: [],
  activeConversationId: null,
  isLoading: false,

  createConversation: (firstMessage?: string) => {
    const id = crypto.randomUUID();
    const now = new Date();
    const conversation: Conversation = {
      id,
      title: firstMessage
        ? firstMessage.length > 50
          ? firstMessage.slice(0, 50) + "..."
          : firstMessage
        : "New Chat",
      messages: [],
      createdAt: now,
      updatedAt: now,
    };
    set((state) => ({
      conversations: [conversation, ...state.conversations],
      activeConversationId: id,
    }));
    return id;
  },

  addMessage: (conversationId: string, message: Message) => {
    set((state) => ({
      conversations: state.conversations.map((conv) =>
        conv.id === conversationId
          ? {
              ...conv,
              messages: [...conv.messages, message],
              updatedAt: new Date(),
            }
          : conv,
      ),
    }));
  },

  updateMessage: (
    conversationId: string,
    messageId: string,
    content: string,
  ) => {
    set((state) => ({
      conversations: state.conversations.map((conv) =>
        conv.id === conversationId
          ? {
              ...conv,
              messages: conv.messages.map((msg) =>
                msg.id === messageId ? { ...msg, content } : msg,
              ),
              updatedAt: new Date(),
            }
          : conv,
      ),
    }));
  },

  setActiveConversation: (id: string | null) => {
    set({ activeConversationId: id });
  },

  getActiveConversation: () => {
    const state = get();
    return state.conversations.find(
      (c) => c.id === state.activeConversationId,
    );
  },

  setLoading: (loading: boolean) => {
    set({ isLoading: loading });
  },
}));

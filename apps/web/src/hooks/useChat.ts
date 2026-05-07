import { useCallback, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { useChatStore } from "@/stores/chatStore";
import { apiClient } from "@/services/api";
import type { Message, Source } from "@/types";

/**
 * Custom hook for chat functionality.
 * Handles sending messages, streaming mock responses, and conversation management.
 */
export function useChat() {
  const conversations = useChatStore((s) => s.conversations);
  const activeConversationId = useChatStore((s) => s.activeConversationId);
  const isLoading = useChatStore((s) => s.isLoading);
  const createConversation = useChatStore((s) => s.createConversation);
  const addMessage = useChatStore((s) => s.addMessage);
  const updateMessage = useChatStore((s) => s.updateMessage);
  const setActiveConversation = useChatStore((s) => s.setActiveConversation);
  const setLoading = useChatStore((s) => s.setLoading);
  const getActiveConversation = useChatStore((s) => s.getActiveConversation);

  const navigate = useNavigate();
  const streamBufferRef = useRef("");
  const abortRef = useRef(false);

  const activeConversation = getActiveConversation();

  const sendMessage = useCallback(
    async (content: string) => {
      if (!content.trim() || isLoading) return;

      const trimmed = content.trim();

      // Create conversation if none is active
      let convId = activeConversationId;
      if (!convId) {
        convId = createConversation(trimmed);
        navigate(`/chat/${convId}`);
      }

      // Add user message
      const userMessage: Message = {
        id: crypto.randomUUID(),
        role: "user",
        content: trimmed,
        timestamp: new Date(),
      };
      addMessage(convId, userMessage);

      // Add placeholder assistant message for streaming
      const assistantMessageId = crypto.randomUUID();
      const assistantMessage: Message = {
        id: assistantMessageId,
        role: "assistant",
        content: "",
        sources: [],
        timestamp: new Date(),
        isStreaming: true,
      };
      addMessage(convId, assistantMessage);

      setLoading(true);
      streamBufferRef.current = "";
      abortRef.current = false;

      try {
        await apiClient.sendMessageStreaming(
          convId,
          trimmed,
          (chunk: string) => {
            if (abortRef.current) return;
            streamBufferRef.current += chunk;
            updateMessage(convId, assistantMessageId, streamBufferRef.current);
          },
          (sources: Source[]) => {
            if (abortRef.current) return;
            // Update sources on the assistant message
            const store = useChatStore.getState();
            const conv = store.conversations.find((c) => c.id === convId);
            if (conv) {
              const msg = conv.messages.find(
                (m) => m.id === assistantMessageId,
              );
              if (msg) {
                msg.sources = sources;
              }
            }
          },
          () => {
            setLoading(false);
            // Mark streaming as complete
            const store = useChatStore.getState();
            const conv = store.conversations.find((c) => c.id === convId);
            if (conv) {
              const msg = conv.messages.find(
                (m) => m.id === assistantMessageId,
              );
              if (msg) {
                msg.isStreaming = false;
              }
            }
          },
        );
      } catch {
        setLoading(false);
        updateMessage(
          convId,
          assistantMessageId,
          "Sorry, something went wrong. Please try again.",
        );
      }
    },
    [
      activeConversationId,
      isLoading,
      createConversation,
      addMessage,
      updateMessage,
      setLoading,
      navigate,
    ],
  );

  return {
    conversations,
    activeConversation,
    activeConversationId,
    messages: activeConversation?.messages ?? [],
    isLoading,
    sendMessage,
    createConversation,
    setActiveConversation,
  };
}

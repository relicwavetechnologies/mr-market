import { useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useChatStore } from '@/stores/chatStore';
import { getMockResponse } from '@/services/mockData';
import type { Message } from '@/types';

export function useChat() {
  const conversations = useChatStore((s) => s.conversations);
  const activeConversationId = useChatStore((s) => s.activeConversationId);
  const messages = useChatStore((s) => s.messages);
  const isGenerating = useChatStore((s) => s.isGenerating);
  const createConversation = useChatStore((s) => s.createConversation);
  const sendMessageToStore = useChatStore((s) => s.sendMessage);
  const updateMessageContent = useChatStore((s) => s.updateMessageContent);
  const updateMessageStreaming = useChatStore((s) => s.updateMessageStreaming);
  const updateMessageSources = useChatStore((s) => s.updateMessageSources);
  const updateMessageCompletionTime = useChatStore((s) => s.updateMessageCompletionTime);
  const setActiveConversation = useChatStore((s) => s.setActiveConversation);
  const setIsGenerating = useChatStore((s) => s.setIsGenerating);

  const navigate = useNavigate();
  const abortRef = useRef(false);

  const currentMessages = activeConversationId
    ? messages[activeConversationId] ?? []
    : [];

  const sendMessage = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || isGenerating) return;

      let convId = activeConversationId;
      if (!convId) {
        convId = createConversation(trimmed);
        navigate(`/chat/${convId}`);
      }

      // Add user message
      const userMessage: Message = {
        id: crypto.randomUUID(),
        role: 'user',
        content: trimmed,
        timestamp: new Date(),
      };
      sendMessageToStore(convId, userMessage);

      // Create assistant placeholder
      const assistantId = crypto.randomUUID();
      const assistantMessage: Message = {
        id: assistantId,
        role: 'assistant',
        content: '',
        sources: [],
        timestamp: new Date(),
        isStreaming: true,
      };
      sendMessageToStore(convId, assistantMessage);

      setIsGenerating(true);
      abortRef.current = false;

      const startTime = performance.now();

      try {
        const mockResponse = getMockResponse(trimmed);

        // Send sources after a short delay
        setTimeout(() => {
          if (!abortRef.current) {
            updateMessageSources(convId!, assistantId, mockResponse.sources);
          }
        }, 300);

        // Stream character by character
        let buffer = '';
        for (let i = 0; i < mockResponse.content.length; i++) {
          if (abortRef.current) break;

          buffer += mockResponse.content[i];
          updateMessageContent(convId!, assistantId, buffer);

          // Variable delay for realistic feel
          const char = mockResponse.content[i];
          let delay: number;
          if (char === '\n') {
            delay = 12 + Math.random() * 18;
          } else if (char === '.' || char === '!' || char === '?') {
            delay = 25 + Math.random() * 30;
          } else if (char === '|' || char === '-') {
            delay = 1 + Math.random() * 3;
          } else {
            delay = 5 + Math.random() * 10;
          }
          await new Promise((resolve) => setTimeout(resolve, delay));
        }

        const elapsed = (performance.now() - startTime) / 1000;
        updateMessageCompletionTime(convId!, assistantId, parseFloat(elapsed.toFixed(1)));
        updateMessageStreaming(convId!, assistantId, false);
      } catch {
        updateMessageContent(convId!, assistantId, 'Sorry, something went wrong. Please try again.');
        updateMessageStreaming(convId!, assistantId, false);
      } finally {
        setIsGenerating(false);
      }
    },
    [
      activeConversationId,
      isGenerating,
      createConversation,
      sendMessageToStore,
      updateMessageContent,
      updateMessageStreaming,
      updateMessageSources,
      updateMessageCompletionTime,
      setActiveConversation,
      setIsGenerating,
      navigate,
    ]
  );

  return {
    conversations,
    messages: currentMessages,
    isGenerating,
    sendMessage,
    createConversation,
    setActiveConversation,
    activeConversationId,
  };
}

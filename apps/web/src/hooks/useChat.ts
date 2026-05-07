import { useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useChatStore } from '@/stores/chatStore';
import { streamChat } from '@/services/chatApi';
import type { ChatStreamEvent, Message, Source, ToolEvent } from '@/types';

export function useChat() {
  const conversations = useChatStore((s) => s.conversations);
  const activeConversationId = useChatStore((s) => s.activeConversationId);
  const messages = useChatStore((s) => s.messages);
  const isGenerating = useChatStore((s) => s.isGenerating);
  const createConversation = useChatStore((s) => s.createConversation);
  const sendMessageToStore = useChatStore((s) => s.sendMessage);
  const patchMessage = useChatStore((s) => s.patchMessage);
  const setActiveConversation = useChatStore((s) => s.setActiveConversation);
  const setIsGenerating = useChatStore((s) => s.setIsGenerating);

  const navigate = useNavigate();
  const abortRef = useRef<AbortController | null>(null);

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

      const userMessage: Message = {
        id: crypto.randomUUID(),
        role: 'user',
        content: trimmed,
        timestamp: new Date(),
      };
      sendMessageToStore(convId, userMessage);

      const assistantId = crypto.randomUUID();
      const assistantMessage: Message = {
        id: assistantId,
        role: 'assistant',
        content: '',
        sources: [],
        toolEvents: [],
        timestamp: new Date(),
        isStreaming: true,
      };
      sendMessageToStore(convId, assistantMessage);

      setIsGenerating(true);
      const startTime = performance.now();

      let content = '';
      const toolEvents: ToolEvent[] = [];
      let intent: string | null = null;
      let ticker: string | null = null;
      const sources: Source[] = [];
      const seenSourceKeys = new Set<string>();
      let finalized = false;

      const finishWith = (patch: Partial<Message>) => {
        if (finalized) return;
        finalized = true;
        const elapsed = (performance.now() - startTime) / 1000;
        patchMessage(convId!, assistantId, {
          ...patch,
          isStreaming: false,
          completionTime: parseFloat(elapsed.toFixed(1)),
        });
        setIsGenerating(false);
      };

      const handleEvent = (ev: ChatStreamEvent) => {
        switch (ev.type) {
          case 'auth':
            return;
          case 'intent':
            intent = ev.intent;
            ticker = ev.ticker;
            patchMessage(convId!, assistantId, { intent, ticker });
            return;
          case 'tool_call': {
            toolEvents.push({ name: ev.name, status: 'running', args: ev.args });
            patchMessage(convId!, assistantId, { toolEvents: [...toolEvents] });
            return;
          }
          case 'tool_result': {
            const idx = toolEvents.findIndex(
              (t) => t.name === ev.name && t.status === 'running',
            );
            const update: ToolEvent = {
              name: ev.name,
              status: 'done',
              ms: ev.ms,
              summary: ev.summary,
              args: idx >= 0 ? toolEvents[idx].args : undefined,
            };
            if (idx >= 0) toolEvents[idx] = update;
            else toolEvents.push(update);

            const summary = ev.summary as Record<string, unknown> | undefined;
            if (summary && typeof summary === 'object') {
              const tickerName =
                (summary.ticker as string | undefined) ?? ev.name;
              if (ev.name === 'get_quote') {
                const conf = (summary.confidence as string) ?? '?';
                const ok = (summary.ok_sources as string[]) ?? [];
                const key = `quote:${tickerName}`;
                if (!seenSourceKeys.has(key)) {
                  seenSourceKeys.add(key);
                  sources.push({
                    title: `${tickerName} — ${conf} confidence (${ok.length} sources)`,
                    domain: 'mr-market',
                  });
                }
              } else if (ev.name === 'get_news') {
                const cnt = (summary.count as number) ?? 0;
                const key = `news:${tickerName}`;
                if (!seenSourceKeys.has(key)) {
                  seenSourceKeys.add(key);
                  sources.push({
                    title: `${tickerName} — ${cnt} headline${cnt === 1 ? '' : 's'} (24h)`,
                    domain: 'mr-market',
                  });
                }
              } else if (ev.name === 'get_company_info') {
                const key = `info:${tickerName}`;
                if (!seenSourceKeys.has(key)) {
                  seenSourceKeys.add(key);
                  sources.push({
                    title: `${tickerName} — fundamentals (yfinance + Screener)`,
                    domain: 'mr-market',
                  });
                }
              }
            }

            patchMessage(convId!, assistantId, {
              toolEvents: [...toolEvents],
              sources: [...sources],
            });
            return;
          }
          case 'delta': {
            content += ev.text ?? '';
            patchMessage(convId!, assistantId, { content });
            return;
          }
          case 'done': {
            finishWith({
              content: ev.message || content,
              blocked: ev.blocked,
              sources: [...sources],
              toolEvents: [...toolEvents],
            });
            return;
          }
          case 'error': {
            finishWith({
              content: content
                ? `${content}\n\n_${ev.message}_`
                : ev.message || 'Something went wrong. Please try again.',
              toolEvents: [...toolEvents],
            });
            return;
          }
        }
      };

      const controller = new AbortController();
      abortRef.current?.abort();
      abortRef.current = controller;

      try {
        await streamChat(trimmed, {
          onEvent: handleEvent,
          signal: controller.signal,
        });
        // Stream ended without a `done`/`error` event — finalize with whatever we have.
        if (!finalized) {
          finishWith({
            content:
              content ||
              'The stream ended unexpectedly. Try asking again.',
            sources: [...sources],
            toolEvents: [...toolEvents],
          });
        }
      } catch (err) {
        if ((err as Error).name !== 'AbortError') {
          finishWith({
            content:
              content ||
              `Stream interrupted: ${(err as Error).message ?? 'unknown error'}`,
          });
        }
      }
    },
    [
      activeConversationId,
      isGenerating,
      createConversation,
      sendMessageToStore,
      patchMessage,
      setIsGenerating,
      navigate,
    ],
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

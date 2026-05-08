import { useEffect, useRef } from 'react';
import { useChatStore } from '@/stores/chatStore';
import { MessageBubble } from './MessageBubble';
import { TypingIndicator } from './TypingIndicator';
import { Separator } from '@/components/ui/separator';

export function ChatContainer() {
  const activeConversationId = useChatStore((s) => s.activeConversationId);
  const messages = useChatStore((s) => s.messages);
  const isGenerating = useChatStore((s) => s.isGenerating);
  const scrollRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const prevCountRef = useRef(0);

  const currentMessages = activeConversationId
    ? messages[activeConversationId] ?? []
    : [];

  useEffect(() => {
    const count = currentMessages.length;
    const isNewMessage = count > prevCountRef.current;
    prevCountRef.current = count;

    if (isNewMessage) {
      scrollRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [currentMessages.length]);

  return (
    <div ref={containerRef} className="flex-1 overflow-y-auto px-6 pb-12 pt-8">
      <div className="mx-auto max-w-3xl space-y-8">
        {currentMessages.map((msg, idx) => (
          <div key={msg.id}>
            {idx > 0 && msg.role === 'user' && <Separator className="mb-8 bg-border/60" />}
            <MessageBubble message={msg} />
          </div>
        ))}
        {isGenerating && currentMessages.length === 0 && <TypingIndicator />}
        <div ref={scrollRef} />
      </div>
    </div>
  );
}

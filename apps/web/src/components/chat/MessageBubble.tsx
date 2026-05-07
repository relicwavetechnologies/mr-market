import { Check, Loader2 } from 'lucide-react';
import type { Message } from '@/types';
import { Disclaimer } from '@/components/common/Disclaimer';
import { parseMarkdown } from '@/utils/parseMarkdown';

interface MessageBubbleProps {
  message: Message;
}

export function MessageBubble({ message }: MessageBubbleProps) {
  if (message.role === 'user') {
    return <UserMessage content={message.content} />;
  }
  return <AssistantMessage message={message} />;
}

function UserMessage({ content }: { content: string }) {
  return (
    <div className="animate-fade-in">
      <h2 className="font-serif text-3xl font-normal leading-snug tracking-tight text-foreground sm:text-[34px]">
        {content}
      </h2>
    </div>
  );
}

function AssistantMessage({ message }: { message: Message }) {
  const { content, sources = [], isStreaming } = message;

  return (
    <div className="animate-fade-in space-y-5">
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        {isStreaming && content.length === 0 ? (
          <>
            <Loader2 className="size-3.5 animate-spin text-foreground/70" />
            <span>Fetching latest data…</span>
          </>
        ) : (
          <>
            <span className="flex size-4 items-center justify-center rounded-full bg-accent">
              <Check className="size-2.5 text-foreground/80" />
            </span>
            <span>Fetched data from {sources.length || 4} sources</span>
          </>
        )}
      </div>

      <div className="answer-copy">
        {parseMarkdown(content, sources)}
        {isStreaming && content.length > 0 && (
          <span className="cursor-blink ml-0.5 text-accent-blue">▍</span>
        )}
      </div>

      {!isStreaming && content.length > 0 && <Disclaimer />}
    </div>
  );
}

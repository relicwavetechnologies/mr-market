import type { Message } from "@/types";
import { Bot, User } from "lucide-react";

interface Props {
  message: Message;
}

/**
 * Renders a single chat message as a bubble.
 * Handles basic markdown-like formatting for code blocks and bold text.
 */
export function MessageBubble({ message }: Props) {
  const isUser = message.role === "user";

  return (
    <div className={`flex gap-3 ${isUser ? "justify-end" : "justify-start"}`}>
      {!isUser && (
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-emerald-900/50">
          <Bot className="h-4 w-4 text-emerald-400" />
        </div>
      )}

      <div
        className={`max-w-[80%] rounded-2xl px-4 py-3 text-sm leading-relaxed ${
          isUser
            ? "bg-emerald-600 text-white"
            : "bg-gray-800 text-gray-200"
        }`}
      >
        <MessageContent content={message.content} />
      </div>

      {isUser && (
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-gray-700">
          <User className="h-4 w-4 text-gray-300" />
        </div>
      )}
    </div>
  );
}

/** Renders message content with basic formatting for code blocks. */
function MessageContent({ content }: { content: string }) {
  if (!content) {
    return <span className="text-gray-500 italic">...</span>;
  }

  // Split on code blocks (```...```)
  const parts = content.split(/(```[\s\S]*?```)/g);

  return (
    <>
      {parts.map((part, i) => {
        if (part.startsWith("```") && part.endsWith("```")) {
          const code = part.slice(3, -3).replace(/^\w+\n/, ""); // strip language hint
          return (
            <pre
              key={i}
              className="my-2 overflow-x-auto rounded-lg bg-gray-900 p-3 text-xs text-gray-300"
            >
              <code>{code}</code>
            </pre>
          );
        }
        // Render bold (**text**)
        const formatted = part.split(/(\*\*[^*]+\*\*)/g).map((seg, j) => {
          if (seg.startsWith("**") && seg.endsWith("**")) {
            return (
              <strong key={j} className="font-semibold text-white">
                {seg.slice(2, -2)}
              </strong>
            );
          }
          return <span key={j}>{seg}</span>;
        });
        return <span key={i}>{formatted}</span>;
      })}
    </>
  );
}

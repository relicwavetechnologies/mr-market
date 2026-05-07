import type { Message } from "@/types";
import { AlertTriangle, Bot, ShieldCheck, User } from "lucide-react";

interface Props {
  message: Message;
}

/**
 * Renders a single chat message as a bubble.
 * Handles basic markdown-like formatting for code blocks and bold text.
 */
export function MessageBubble({ message }: Props) {
  const isUser = message.role === "user";
  const g = message.guardrail;
  const showOverride = g?.overridden;
  const showMismatchHint = !showOverride && (g?.claim_mismatches?.length ?? 0) > 0;

  return (
    <div className={`flex gap-3 ${isUser ? "justify-end" : "justify-start"}`}>
      {!isUser && (
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-emerald-900/50">
          <Bot className="h-4 w-4 text-emerald-400" />
        </div>
      )}

      <div className={`flex max-w-[80%] flex-col gap-2`}>
        {showOverride && (
          <div className="flex items-start gap-2 rounded-md border border-amber-700/40 bg-amber-900/20 px-3 py-2 text-xs text-amber-200">
            <AlertTriangle size={13} className="mt-0.5 shrink-0 text-amber-400" />
            <div>
              <div className="font-medium">Replaced for compliance</div>
              <div className="text-amber-200/80">
                The model's draft contained{" "}
                {g?.blocklist_hits?.[0]?.category ?? "advice"} language. The
                streamed text was overridden with a SEBI-safe response.{" "}
                {g?.blocklist_hits?.length ? (
                  <span className="text-amber-300/80">
                    ({g.blocklist_hits.map((h) => h.rule_id).join(", ")})
                  </span>
                ) : null}
              </div>
            </div>
          </div>
        )}
        {showMismatchHint && (
          <div className="flex items-start gap-2 rounded-md border border-sky-700/40 bg-sky-900/20 px-3 py-2 text-[11px] text-sky-200">
            <ShieldCheck size={12} className="mt-0.5 shrink-0 text-sky-400" />
            <div>
              Verifier flagged {g!.claim_mismatches.length} number
              {g!.claim_mismatches.length === 1 ? "" : "s"} not seen in the
              tool results. Logged for audit.
            </div>
          </div>
        )}
        <div
          className={`rounded-2xl px-4 py-3 text-sm leading-relaxed ${
            isUser
              ? "bg-emerald-600 text-white"
              : "bg-gray-800 text-gray-200"
          }`}
        >
          <MessageContent content={message.content} />
        </div>
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

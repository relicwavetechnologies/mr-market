import type { Source } from "@/types";

/**
 * Stream a chat response from the backend `/chat` SSE endpoint.
 *
 * SSE event payloads (one JSON per `data:` line):
 *   {type:"intent",       intent, ticker}
 *   {type:"tool_call",    name, args}
 *   {type:"tool_result",  name, ms, summary}
 *   {type:"delta",        text}
 *   {type:"done",         message, tool_results, blocked}
 *   {type:"error",        message}
 *
 * `onChunk` receives raw answer-text deltas (just the assistant's words).
 * `onSources` receives a synthesised source list once tool calls finish.
 * `onMeta` lets the UI peek at intent/tool-call/tool-result events.
 */
export type ChatFinal = {
  message: string;        // canonical final assistant text (post-guardrail override if any)
  blocked: boolean;       // true if guardrails replaced the streamed answer
  guardrail?: GuardrailMeta;
};

export type GuardrailMeta = {
  overridden: boolean;
  disclaimer_injected: boolean;
  blocklist_hits: { rule_id: string; category: string; matched: string }[];
  claim_mismatches: {
    raw: string;
    value: string;
    unit: string | null;
    closest: string | null;
    delta_pct: string | null;
  }[];
  router_short_circuit?: boolean;
};

export async function streamChat(
  message: string,
  onChunk: (text: string) => void,
  onSources: (sources: Source[]) => void,
  onDone: (final?: ChatFinal) => void,
  onMeta?: (event: ChatStreamEvent) => void,
): Promise<void> {
  const res = await fetch("/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify({ message }),
  });
  if (!res.ok || !res.body) {
    onChunk(`Sorry, I hit a backend error (${res.status}). Try again in a moment.`);
    onDone();
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  const collectedSources: Source[] = [];
  const seenUrls = new Set<string>();
  let lastGuardrail: GuardrailMeta | undefined;

  // Read SSE byte stream → split on blank lines → parse `data: {...}`.
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });

    let idx: number;
    while ((idx = buf.indexOf("\n\n")) !== -1) {
      const block = buf.slice(0, idx);
      buf = buf.slice(idx + 2);
      const dataLines = block
        .split("\n")
        .filter((l) => l.startsWith("data:"))
        .map((l) => l.slice(5).trimStart());
      if (dataLines.length === 0) continue;
      const raw = dataLines.join("\n");
      let evt: ChatStreamEvent;
      try {
        evt = JSON.parse(raw);
      } catch {
        continue;
      }

      onMeta?.(evt);

      switch (evt.type) {
        case "delta":
          onChunk(evt.text ?? "");
          break;
        case "tool_result":
          if (evt.summary && typeof evt.summary === "object") {
            const ticker =
              (evt.summary as { ticker?: string }).ticker ?? evt.name;
            if (evt.name === "get_news") {
              const cnt = (evt.summary as { count?: number }).count ?? 0;
              const url = "/news/" + ticker;
              if (!seenUrls.has(url)) {
                seenUrls.add(url);
                collectedSources.push({
                  title: `${ticker} — ${cnt} headline${cnt === 1 ? "" : "s"} (last 24h)`,
                });
              }
            } else if (evt.name === "get_quote") {
              const conf = (evt.summary as { confidence?: string }).confidence ?? "?";
              const ok = (evt.summary as { ok_sources?: string[] }).ok_sources ?? [];
              const url = "/quote/" + ticker;
              if (!seenUrls.has(url)) {
                seenUrls.add(url);
                collectedSources.push({
                  title: `${ticker} — ${conf} confidence (${ok.length} sources)`,
                });
              }
            } else if (evt.name === "get_company_info") {
              const url = "/info/" + ticker;
              if (!seenUrls.has(url)) {
                seenUrls.add(url);
                collectedSources.push({
                  title: `${ticker} — fundamentals (yfinance + Screener)`,
                });
              }
            }
          }
          break;
        case "done":
          if (collectedSources.length) onSources(collectedSources);
          onDone({
            message: (evt as { message?: string }).message ?? "",
            blocked: Boolean((evt as { blocked?: boolean }).blocked),
            guardrail: lastGuardrail,
          });
          return;
        case "error":
          onChunk(`\n\n_${evt.message ?? "Backend error."}_`);
          onDone();
          return;
        case "guardrail": {
          const g = evt as unknown as GuardrailMeta & { type: "guardrail" };
          lastGuardrail = {
            overridden: Boolean(g.overridden),
            disclaimer_injected: Boolean(g.disclaimer_injected),
            blocklist_hits: g.blocklist_hits ?? [],
            claim_mismatches: g.claim_mismatches ?? [],
            router_short_circuit: g.router_short_circuit,
          };
          break;
        }
        default:
          break;
      }
    }
  }
  // Stream ended without an explicit `done` event — close out.
  if (collectedSources.length) onSources(collectedSources);
  onDone();
  // Mark vars referenced for completeness; lastGuardrail not propagated here.
  void lastGuardrail;
}


export type ChatStreamEvent =
  | { type: "auth"; source: string }
  | { type: "intent"; intent: string | null; ticker: string | null }
  | { type: "tool_call"; name: string; args: Record<string, unknown> }
  | {
      type: "tool_result";
      name: string;
      ms: number;
      summary: Record<string, unknown>;
    }
  | { type: "delta"; text: string }
  | ({ type: "guardrail" } & GuardrailMeta)
  | {
      type: "done";
      message: string;
      tool_results: Record<string, unknown>;
      blocked: boolean;
    }
  | { type: "error"; message: string };


// Back-compat surface for the existing useChat hook.
class ApiClient {
  async sendMessageStreaming(
    _conversationId: string,
    message: string,
    onChunk: (chunk: string) => void,
    onSources: (sources: Source[]) => void,
    onDone: (final?: ChatFinal) => void,
  ): Promise<void> {
    return streamChat(message, onChunk, onSources, onDone);
  }

  async getHealth(): Promise<{ status: string }> {
    const r = await fetch("/healthz");
    if (!r.ok) return { status: "unhealthy" };
    return r.json();
  }
}

export const apiClient = new ApiClient();

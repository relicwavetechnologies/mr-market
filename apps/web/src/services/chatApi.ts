import type { ChatStreamEvent } from '@/types';
import { apiFetch } from './apiClient';

interface StreamChatHandlers {
  onEvent: (event: ChatStreamEvent) => void;
  signal?: AbortSignal;
  conversationId?: string | null;
}

export async function streamChat(
  message: string,
  { onEvent, signal, conversationId }: StreamChatHandlers,
): Promise<void> {
  let res: Response;
  try {
    res = await apiFetch('/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
      body: JSON.stringify({ message, conversation_id: conversationId ?? null }),
      signal,
    });
  } catch (err) {
    if ((err as Error).name === 'AbortError') return;
    onEvent({
      type: 'error',
      message: `Network error: ${(err as Error).message}. Is the backend running on :8001?`,
    });
    return;
  }

  if (!res.ok || !res.body) {
    onEvent({
      type: 'error',
      message: `Backend returned ${res.status}. ${res.statusText || 'Try again in a moment.'}`,
    });
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = '';

  while (true) {
    let chunk: ReadableStreamReadResult<Uint8Array>;
    try {
      chunk = await reader.read();
    } catch (err) {
      if ((err as Error).name === 'AbortError') return;
      throw err;
    }
    if (chunk.done) break;
    buf += decoder.decode(chunk.value, { stream: true });

    // SSE event blocks are separated by a blank line. Per the spec, line
    // endings can be \r\n, \n, or \r — we accept all three.
    const splitRe = /\r\n\r\n|\n\n|\r\r/;
    let m: RegExpExecArray | null;
    while ((m = splitRe.exec(buf)) !== null) {
      const block = buf.slice(0, m.index);
      buf = buf.slice(m.index + m[0].length);
      const dataLines = block
        .split(/\r\n|\n|\r/)
        .filter((l) => l.startsWith('data:'))
        .map((l) => l.slice(5).trimStart());
      if (!dataLines.length) continue;
      const raw = dataLines.join('\n');
      let evt: ChatStreamEvent;
      try {
        evt = JSON.parse(raw) as ChatStreamEvent;
      } catch {
        continue;
      }
      onEvent(evt);
      if (evt.type === 'done' || evt.type === 'error') return;
    }
  }
}

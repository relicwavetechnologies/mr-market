type MessageHandler = (data: Record<string, unknown>) => void;

/**
 * Manages a WebSocket connection for streaming chat responses.
 *
 * Protocol (mirrors the FastAPI WebSocket endpoint):
 *   Client sends:  { "message": "...", "conversation_id": "..." }
 *   Server sends:  { "type": "chunk", "content": "..." }
 *   Server sends:  { "type": "done", "conversation_id": "...", "sources": [...] }
 */
export class WebSocketManager {
  private ws: WebSocket | null = null;
  private url: string;
  private handlers: Set<MessageHandler> = new Set();
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private reconnectDelay = 1000;
  private shouldReconnect = true;

  constructor(url?: string) {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    this.url =
      url ?? `${protocol}//${window.location.host}/api/v1/chat/ws`;
  }

  /** Register a handler that is called for every incoming message. */
  onMessage(handler: MessageHandler): () => void {
    this.handlers.add(handler);
    return () => this.handlers.delete(handler);
  }

  /** Open the WebSocket connection. */
  connect(token?: string): void {
    if (this.ws?.readyState === WebSocket.OPEN) return;

    const urlWithToken = token
      ? `${this.url}?token=${encodeURIComponent(token)}`
      : this.url;

    this.ws = new WebSocket(urlWithToken);

    this.ws.onopen = () => {
      this.reconnectAttempts = 0;
    };

    this.ws.onmessage = (event: MessageEvent) => {
      try {
        const data = JSON.parse(event.data) as Record<string, unknown>;
        this.handlers.forEach((h) => h(data));
      } catch {
        // ignore malformed messages
      }
    };

    this.ws.onclose = () => {
      if (this.shouldReconnect && this.reconnectAttempts < this.maxReconnectAttempts) {
        this.reconnectAttempts++;
        const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1);
        setTimeout(() => this.connect(token), delay);
      }
    };

    this.ws.onerror = () => {
      // onclose will fire after onerror — reconnection is handled there
    };
  }

  /** Send a JSON payload over the connection. */
  send(data: Record<string, unknown>): void {
    if (this.ws?.readyState !== WebSocket.OPEN) {
      throw new Error("WebSocket is not connected");
    }
    this.ws.send(JSON.stringify(data));
  }

  /** Gracefully close the connection without auto-reconnect. */
  disconnect(): void {
    this.shouldReconnect = false;
    this.ws?.close();
    this.ws = null;
  }

  /** Returns true if the socket is open and ready. */
  get isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }
}

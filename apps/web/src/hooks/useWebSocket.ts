import { useEffect, useRef, useCallback, useState } from "react";
import { WebSocketManager } from "@/services/websocket";

interface UseWebSocketOptions {
  /** URL override; defaults to the chat WS endpoint. */
  url?: string;
  /** Auth token passed as a query parameter. */
  token?: string;
  /** Whether to automatically connect on mount. */
  autoConnect?: boolean;
}

/**
 * Low-level hook that wraps WebSocketManager with React lifecycle.
 * Handles connect/disconnect on mount/unmount and exposes send + message state.
 */
export function useWebSocket(options: UseWebSocketOptions = {}) {
  const { url, token, autoConnect = true } = options;
  const managerRef = useRef<WebSocketManager | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [lastMessage, setLastMessage] = useState<Record<string, unknown> | null>(null);

  useEffect(() => {
    const manager = new WebSocketManager(url);
    managerRef.current = manager;

    const unsubscribe = manager.onMessage((data) => {
      setLastMessage(data);
    });

    // Poll connection status
    const interval = setInterval(() => {
      setIsConnected(manager.isConnected);
    }, 500);

    if (autoConnect) {
      manager.connect(token);
    }

    return () => {
      clearInterval(interval);
      unsubscribe();
      manager.disconnect();
    };
  }, [url, token, autoConnect]);

  const send = useCallback((data: Record<string, unknown>) => {
    managerRef.current?.send(data);
  }, []);

  const connect = useCallback(() => {
    managerRef.current?.connect(token);
  }, [token]);

  const disconnect = useCallback(() => {
    managerRef.current?.disconnect();
  }, []);

  return { send, lastMessage, isConnected, connect, disconnect };
}

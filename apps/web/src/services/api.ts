import axios, { type AxiosInstance } from "axios";
import type { Conversation, Message, Source } from "@/types";
import { streamMockResponse } from "./mockData";

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "/api/v1";

class ApiClient {
  private http: AxiosInstance;

  constructor() {
    this.http = axios.create({
      baseURL: BASE_URL,
      headers: { "Content-Type": "application/json" },
      timeout: 30_000,
    });
  }

  /** Send a chat message and stream the response via mock data. */
  async sendMessageStreaming(
    _conversationId: string,
    message: string,
    onChunk: (chunk: string) => void,
    onSources: (sources: Source[]) => void,
    onDone: () => void,
  ): Promise<void> {
    // For now, use mock streaming responses
    await streamMockResponse(message, onChunk, onSources, onDone);
  }

  /** Fetch a single conversation by ID. */
  async getConversation(id: string): Promise<Conversation | null> {
    try {
      const { data } = await this.http.get<Conversation>(
        `/conversations/${id}`,
      );
      return data;
    } catch {
      return null;
    }
  }

  /** Fetch all conversations. */
  async getConversations(): Promise<Conversation[]> {
    try {
      const { data } = await this.http.get<Conversation[]>("/conversations");
      return data;
    } catch {
      return [];
    }
  }

  /** Send a chat message (non-streaming fallback). */
  async sendMessage(
    message: string,
    conversationId?: string,
  ): Promise<{ message: string; sources: Array<{ label: string; url?: string }> }> {
    const { data } = await this.http.post("/chat", {
      message,
      conversation_id: conversationId,
    });
    return data as { message: string; sources: Array<{ label: string; url?: string }> };
  }

  /** Health check. */
  async getHealth(): Promise<{ status: string }> {
    const { data } = await this.http.get<{ status: string }>("/health");
    return data;
  }
}

// Suppress unused variable warnings -- these types are re-exported for convenience
void (undefined as unknown as Message);
void (undefined as unknown as Conversation);

export const apiClient = new ApiClient();

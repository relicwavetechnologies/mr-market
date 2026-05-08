import { useEffect, useRef } from 'react';
import { useParams, useLocation, useNavigate } from 'react-router-dom';
import { Plus, Share2 } from 'lucide-react';
import { ChatContainer } from '@/components/chat/ChatContainer';
import { ChatInput } from '@/components/chat/ChatInput';
import { AuthBanner } from '@/components/common/AuthBanner';
import { ToastIsland } from '@/components/common/ToastIsland';
import { Button } from '@/components/ui/button';
import { useChatStore } from '@/stores/chatStore';
import { useChat } from '@/hooks/useChat';

export function ChatPage() {
  const { id } = useParams<{ id: string }>();
  const location = useLocation();
  const navigate = useNavigate();
  const setActiveConversation = useChatStore((s) => s.setActiveConversation);
  const fetchConversation = useChatStore((s) => s.fetchConversation);
  const storedMessages = useChatStore((s) => (id ? s.messages[id] : undefined));
  const { sendMessage, isGenerating } = useChat();
  const consumedInitialFor = useRef<string | null>(null);

  useEffect(() => {
    if (id) {
      setActiveConversation(id);
      if (!storedMessages || storedMessages.length === 0) {
        void fetchConversation(id).catch(() => undefined);
      }
    }
  }, [id, setActiveConversation, fetchConversation, storedMessages]);

  useEffect(() => {
    const state = location.state as { initialQuery?: string } | null;
    if (!state?.initialQuery || !id) return;
    if (consumedInitialFor.current === id) return;
    consumedInitialFor.current = id;
    sendMessage(state.initialQuery);
    navigate(`/chat/${id}`, { replace: true, state: {} });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const handleNewChat = () => {
    setActiveConversation(null);
    navigate('/');
  };

  return (
    <div className="flex flex-1 flex-col overflow-hidden bg-background">
      <header className="flex h-12 shrink-0 items-center justify-end border-b border-border/60 px-4">
        <div className="flex items-center gap-2">
          <AuthBanner />
          <Button
            variant="outline"
            size="sm"
            className="h-8 gap-1.5 border-border/80 bg-transparent text-xs text-muted-foreground hover:text-foreground"
          >
            <Share2 className="size-3.5" />
            <span>Share</span>
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={handleNewChat}
            className="h-8 gap-1.5 border-border/80 bg-transparent text-xs text-muted-foreground hover:text-foreground"
          >
            <Plus className="size-3.5" />
            <span>New</span>
          </Button>
        </div>
      </header>

      <ChatContainer />

      <div className="shrink-0 px-6 pb-2">
        <div className="mx-auto max-w-3xl">
          <ToastIsland />
          <ChatInput
            onSubmit={sendMessage}
            placeholder="Ask a follow-up..."
            disabled={isGenerating}
            conversationId={id}
          />
          <p className="mt-1.5 text-center text-[10px] leading-tight text-muted-foreground/80">
            Midas is AI and can make mistakes. Verify before acting — not investment advice.
          </p>
        </div>
      </div>
    </div>
  );
}

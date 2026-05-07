import { useEffect, useRef, useState } from 'react';
import { useParams, useLocation, useNavigate } from 'react-router-dom';
import {
  BarChart3,
  Link as LinkIcon,
  Plus,
  Share2,
  Sparkles,
} from 'lucide-react';
import { ChatContainer } from '@/components/chat/ChatContainer';
import { ChatInput } from '@/components/chat/ChatInput';
import { AuthBanner } from '@/components/common/AuthBanner';
import { Button } from '@/components/ui/button';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { useChatStore } from '@/stores/chatStore';
import { useChat } from '@/hooks/useChat';

const TABS = [
  { id: 'answer', label: 'Answer', icon: Sparkles },
  { id: 'sources', label: 'Sources', icon: LinkIcon },
  { id: 'charts', label: 'Charts', icon: BarChart3 },
] as const;

export function ChatPage() {
  const { id } = useParams<{ id: string }>();
  const location = useLocation();
  const navigate = useNavigate();
  const setActiveConversation = useChatStore((s) => s.setActiveConversation);
  const fetchConversation = useChatStore((s) => s.fetchConversation);
  const storedMessages = useChatStore((s) => (id ? s.messages[id] : undefined));
  const { sendMessage, isGenerating } = useChat();
  const [activeTab, setActiveTab] = useState<string>('answer');
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
      <header className="flex h-12 shrink-0 items-center justify-between border-b border-border/60 px-4">
        <Tabs value={activeTab} onValueChange={setActiveTab}>
          <TabsList className="h-9 gap-0 bg-transparent p-0">
            {TABS.map((tab) => {
              const Icon = tab.icon;
              return (
                <TabsTrigger
                  key={tab.id}
                  value={tab.id}
                  className="gap-2 rounded-md px-3 text-[13px] font-normal text-muted-foreground data-[state=active]:bg-accent data-[state=active]:text-foreground data-[state=active]:shadow-none"
                >
                  <Icon className="size-3.5" />
                  <span>{tab.label}</span>
                </TabsTrigger>
              );
            })}
          </TabsList>
        </Tabs>

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
          <ChatInput
            onSubmit={sendMessage}
            placeholder="Ask a follow-up..."
            disabled={isGenerating}
          />
          <p className="mt-1.5 text-center text-[10px] leading-tight text-muted-foreground/80">
            Midas is AI and can make mistakes. Verify before acting — not investment advice.
          </p>
        </div>
      </div>
    </div>
  );
}

import { useNavigate, useLocation } from "react-router-dom";
import {
  Plus,
  BookOpen,
  History,
  MessageSquare,
  PanelLeftClose,
  PanelLeft,
  TrendingUp,
  Sparkles,
} from "lucide-react";
import { useUIStore } from "@/stores/uiStore";
import { useChatStore } from "@/stores/chatStore";

export function Sidebar() {
  const sidebarOpen = useUIStore((s) => s.sidebarOpen);
  const toggleSidebar = useUIStore((s) => s.toggleSidebar);
  const conversations = useChatStore((s) => s.conversations);
  const activeConversationId = useChatStore((s) => s.activeConversationId);
  const setActiveConversation = useChatStore((s) => s.setActiveConversation);

  const navigate = useNavigate();
  const location = useLocation();

  const handleNewChat = () => {
    setActiveConversation(null);
    navigate("/");
  };

  const handleConversationClick = (id: string) => {
    setActiveConversation(id);
    navigate(`/chat/${id}`);
  };

  const isHome = location.pathname === "/";

  return (
    <>
      {/* Toggle button for collapsed state */}
      {!sidebarOpen && (
        <button
          onClick={toggleSidebar}
          className="fixed left-3 top-3 z-40 rounded-lg p-2 text-text-secondary transition-colors hover:bg-bg-hover hover:text-text-primary"
          aria-label="Open sidebar"
        >
          <PanelLeft size={20} />
        </button>
      )}

      {/* Sidebar panel */}
      <aside
        className={`flex h-full flex-col border-r border-border-subtle bg-bg-secondary transition-all duration-300 ${
          sidebarOpen ? "w-[260px] min-w-[260px]" : "w-0 min-w-0 overflow-hidden"
        }`}
      >
        <div className="flex h-full flex-col">
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3">
            <div className="flex items-center gap-2">
              <TrendingUp size={20} className="text-accent" />
              <span className="text-sm font-semibold text-text-primary">
                Mr. Market
              </span>
            </div>
            <button
              onClick={toggleSidebar}
              className="rounded-lg p-1.5 text-text-secondary transition-colors hover:bg-bg-hover hover:text-text-primary"
              aria-label="Close sidebar"
            >
              <PanelLeftClose size={18} />
            </button>
          </div>

          {/* New Chat button */}
          <div className="px-3 pb-2">
            <button
              onClick={handleNewChat}
              className="flex w-full items-center gap-2 rounded-lg border border-border bg-bg-tertiary px-3 py-2 text-sm text-text-primary transition-colors hover:bg-bg-hover"
            >
              <Plus size={16} />
              <span>New Chat</span>
            </button>
          </div>

          {/* Nav items */}
          <nav className="px-3 pb-2">
            <button
              onClick={() => navigate("/")}
              className={`flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition-colors ${
                isHome
                  ? "bg-bg-hover text-text-primary"
                  : "text-text-secondary hover:bg-bg-hover hover:text-text-primary"
              }`}
            >
              <BookOpen size={16} />
              <span>Library</span>
            </button>
            <button
              className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-sm text-text-secondary transition-colors hover:bg-bg-hover hover:text-text-primary"
            >
              <History size={16} />
              <span>History</span>
            </button>
          </nav>

          {/* Divider */}
          <div className="mx-3 border-t border-border-subtle" />

          {/* Chat history */}
          <div className="flex-1 overflow-y-auto px-3 py-2">
            {conversations.length === 0 ? (
              <p className="px-3 py-4 text-center text-xs text-text-muted">
                No conversations yet
              </p>
            ) : (
              <div className="space-y-0.5">
                {conversations.map((conv) => (
                  <button
                    key={conv.id}
                    onClick={() => handleConversationClick(conv.id)}
                    className={`flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm transition-colors ${
                      conv.id === activeConversationId
                        ? "bg-bg-hover text-text-primary"
                        : "text-text-secondary hover:bg-bg-hover hover:text-text-primary"
                    }`}
                  >
                    <MessageSquare size={14} className="shrink-0" />
                    <span className="truncate">{conv.title}</span>
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Footer (auth deferred to Phase 2 — Guest only for demo) */}
          <div className="border-t border-border-subtle p-3">
            <div className="flex items-center gap-3 rounded-lg px-2 py-2">
              <div className="flex h-8 w-8 items-center justify-center rounded-full bg-bg-tertiary text-sm font-medium text-text-primary">
                G
              </div>
              <div className="flex-1 overflow-hidden">
                <p className="truncate text-sm text-text-primary">Guest</p>
                <p className="truncate text-xs text-text-muted">demo build</p>
              </div>
              <span className="flex items-center gap-1 rounded-full bg-accent/10 px-2 py-0.5 text-[10px] font-medium text-accent">
                <Sparkles size={10} />
                Demo
              </span>
            </div>
          </div>
        </div>
      </aside>
    </>
  );
}

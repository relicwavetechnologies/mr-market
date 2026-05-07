import { useNavigate } from 'react-router-dom';
import {
  ArrowUpRight,
  Briefcase,
  Clock,
  Compass,
  LogOut,
  Moon,
  PanelLeft,
  PanelLeftClose,
  Pencil,
  Settings,
  Star,
  Sun,
  TrendingUp,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { useUIStore } from '@/stores/uiStore';
import { useChatStore } from '@/stores/chatStore';
import { useAuthStore } from '@/stores/authStore';
import { useThemeStore } from '@/stores/themeStore';
import { cn } from '@/lib/utils';

interface NavItem {
  icon: LucideIcon;
  label: string;
}

const NAV_ITEMS: NavItem[] = [
  { icon: TrendingUp, label: 'Markets' },
  { icon: Star, label: 'Watchlist' },
  { icon: Briefcase, label: 'Portfolio' },
  { icon: Compass, label: 'Discover' },
];

export function Sidebar() {
  const sidebarOpen = useUIStore((s) => s.sidebarOpen);
  const toggleSidebar = useUIStore((s) => s.toggleSidebar);
  const conversations = useChatStore((s) => s.conversations);
  const activeConversationId = useChatStore((s) => s.activeConversationId);
  const setActiveConversation = useChatStore((s) => s.setActiveConversation);
  const fetchConversation = useChatStore((s) => s.fetchConversation);
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const setShowAuthModal = useAuthStore((s) => s.setShowAuthModal);
  const theme = useThemeStore((s) => s.theme);
  const toggleTheme = useThemeStore((s) => s.toggleTheme);

  const navigate = useNavigate();

  const handleNewChat = () => {
    setActiveConversation(null);
    navigate('/');
  };

  const handleConversationClick = (id: string) => {
    setActiveConversation(id);
    navigate(`/chat/${id}`);
    void fetchConversation(id).catch(() => undefined);
  };

  if (!sidebarOpen) {
    return (
      <aside className="flex h-full w-14 min-w-14 flex-col items-center border-r border-border bg-sidebar py-3">
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={toggleSidebar}
              className="text-muted-foreground hover:text-foreground"
              aria-label="Open sidebar"
            >
              <PanelLeft className="size-4" />
            </Button>
          </TooltipTrigger>
          <TooltipContent side="right">Expand sidebar</TooltipContent>
        </Tooltip>

        <div className="mt-2 flex h-8 w-8 items-center justify-center rounded-md bg-foreground/10">
          <TrendingUp className="size-4 text-foreground" />
        </div>

        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={handleNewChat}
              className="mt-3 text-muted-foreground hover:text-foreground"
              aria-label="New chat"
            >
              <Pencil className="size-4" />
            </Button>
          </TooltipTrigger>
          <TooltipContent side="right">New thread</TooltipContent>
        </Tooltip>

        <div className="mt-auto flex flex-col items-center gap-2">
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon-sm"
                onClick={toggleTheme}
                className="text-muted-foreground hover:text-foreground"
                aria-label="Toggle theme"
              >
                {theme === 'dark' ? <Sun className="size-4" /> : <Moon className="size-4" />}
              </Button>
            </TooltipTrigger>
            <TooltipContent side="right">
              {theme === 'dark' ? 'Light mode' : 'Dark mode'}
            </TooltipContent>
          </Tooltip>
          <button
            onClick={() => (user ? undefined : setShowAuthModal(true))}
            className="flex h-8 w-8 items-center justify-center rounded-full bg-foreground/10 text-xs font-medium text-foreground transition-colors hover:bg-foreground/20"
            title={user?.name ?? 'Sign in'}
          >
            {user?.name ? user.name.charAt(0).toUpperCase() : 'G'}
          </button>
          {user && (
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  onClick={logout}
                  className="text-muted-foreground hover:text-foreground"
                  aria-label="Sign out"
                >
                  <LogOut className="size-4" />
                </Button>
              </TooltipTrigger>
              <TooltipContent side="right">Sign out</TooltipContent>
            </Tooltip>
          )}
        </div>
      </aside>
    );
  }

  const userName = user?.name ?? 'Guest';
  const userInitial = userName.charAt(0).toUpperCase();
  const userEmail = user?.email ?? 'Sign in';

  return (
    <aside className="flex h-full w-[244px] min-w-[244px] flex-col border-r border-border bg-sidebar">
      {/* Header / logo */}
      <div className="flex h-12 items-center justify-between px-4">
        <button
          onClick={handleNewChat}
          className="flex items-center gap-2 outline-none"
          aria-label="Midas home"
        >
          <span className="flex size-6 items-center justify-center rounded-md bg-foreground/10">
            <TrendingUp className="size-3.5 text-foreground" />
          </span>
          <span className="text-[13px] font-medium tracking-tight text-foreground">
            Midas
          </span>
        </button>
        <Button
          variant="ghost"
          size="icon-xs"
          onClick={toggleSidebar}
          className="text-muted-foreground hover:text-foreground"
          aria-label="Collapse sidebar"
        >
          <PanelLeftClose className="size-3.5" />
        </Button>
      </div>

      {/* Primary nav */}
      <nav className="px-2 pt-1">
        <Button
          variant="ghost"
          onClick={handleNewChat}
          className="h-9 w-full justify-start gap-3 px-3 text-[13px] font-medium text-foreground hover:bg-accent"
        >
          <Pencil className="size-4 text-muted-foreground" />
          <span>New</span>
        </Button>
        {NAV_ITEMS.map((item) => (
          <Button
            key={item.label}
            variant="ghost"
            className="h-9 w-full justify-start gap-3 px-3 text-[13px] font-normal text-muted-foreground hover:bg-accent hover:text-foreground"
          >
            <item.icon className="size-4" />
            <span>{item.label}</span>
          </Button>
        ))}
      </nav>

      {/* History */}
      <div className="flex min-h-0 flex-1 flex-col pt-2">
        <div className="flex h-8 items-center gap-3 px-5 text-[13px] text-muted-foreground">
          <Clock className="size-4" />
          <span>History</span>
        </div>
        <ScrollArea className="flex-1">
          <div className="px-3 pb-3">
            {conversations.length === 0 ? (
              <p className="px-2 py-2 text-xs text-muted-foreground/70">No history yet</p>
            ) : (
              <ul className="flex flex-col gap-px">
                {conversations.map((conv) => (
                  <li key={conv.id}>
                    <button
                      onClick={() => handleConversationClick(conv.id)}
                      className={cn(
                        'flex h-7 w-full items-center rounded-md px-2 text-left text-[12.5px] transition-colors',
                        conv.id === activeConversationId
                          ? 'bg-accent text-foreground'
                          : 'text-muted-foreground hover:bg-accent/60 hover:text-foreground',
                      )}
                      title={conv.title}
                    >
                      <span className="truncate">{conv.title}</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </ScrollArea>
      </div>

      {/* Footer: upgrade + user */}
      <div className="px-3 pb-3 pt-2">
        <Button
          variant="outline"
          className="mb-2 h-8 w-full justify-start gap-2 rounded-full border-border/80 bg-transparent px-3 text-xs text-muted-foreground hover:bg-accent hover:text-foreground"
        >
          <ArrowUpRight className="size-3.5" />
          <span>Upgrade plan</span>
          <span className="ml-auto size-1.5 rounded-full bg-teal" aria-hidden />
        </Button>

        <div
          onClick={() => (user ? undefined : setShowAuthModal(true))}
          className="flex cursor-pointer items-center gap-2 rounded-md px-1 py-1 transition-colors hover:bg-accent"
        >
          <div className="flex size-7 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-teal to-accent-blue text-[11px] font-medium text-background">
            {userInitial}
          </div>
          <div className="min-w-0 flex-1 leading-tight">
            <p className="truncate text-[12px] font-medium text-foreground">{userName}</p>
            {!user && <p className="truncate text-[10px] text-muted-foreground">{userEmail}</p>}
          </div>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon-xs"
                onClick={(e) => {
                  e.stopPropagation();
                  toggleTheme();
                }}
                className="text-muted-foreground hover:text-foreground"
                aria-label="Toggle theme"
              >
                {theme === 'dark' ? <Sun className="size-3.5" /> : <Moon className="size-3.5" />}
              </Button>
            </TooltipTrigger>
            <TooltipContent>{theme === 'dark' ? 'Light mode' : 'Dark mode'}</TooltipContent>
          </Tooltip>
          <Button
            variant="ghost"
            size="icon-xs"
            onClick={(e) => {
              e.stopPropagation();
              if (user) logout();
            }}
            className="text-muted-foreground hover:text-foreground"
            aria-label={user ? 'Sign out' : 'Settings'}
          >
            {user ? <LogOut className="size-3.5" /> : <Settings className="size-3.5" />}
          </Button>
        </div>
      </div>
    </aside>
  );
}

import { useNavigate } from 'react-router-dom';
import { SearchInput } from '@/components/home/SearchInput';
import { SuggestionChips } from '@/components/home/SuggestionChips';
import { AuthBanner } from '@/components/common/AuthBanner';
import { useChatStore } from '@/stores/chatStore';

export function HomePage() {
  const navigate = useNavigate();
  const createConversation = useChatStore((s) => s.createConversation);

  const handleSubmit = (query: string) => {
    const id = createConversation(query);
    navigate(`/chat/${id}`, { state: { initialQuery: query } });
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-y-auto bg-background">
      <header className="flex h-12 shrink-0 items-center justify-end border-b border-border/40 px-4">
        <AuthBanner />
      </header>
      <div className="flex flex-1 flex-col items-center justify-center px-6 pb-32 pt-16">
        <div className="w-full max-w-[720px]">
          <h1 className="mb-8 text-center font-serif text-[68px] font-normal leading-none tracking-[-0.03em] text-foreground sm:text-[80px]">
            Midas
          </h1>

          <div className="mb-2">
            <SearchInput onSubmit={handleSubmit} placeholder="Ask anything..." autoFocus />
          </div>

          <p className="mb-4 mt-1.5 text-center text-[10px] leading-tight text-muted-foreground/80">
            Midas is AI and can make mistakes. Verify before acting — not investment advice.
          </p>

          <SuggestionChips onChipClick={handleSubmit} />
        </div>
      </div>
    </div>
  );
}

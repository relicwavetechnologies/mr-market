import { SearchInput } from '@/components/home/SearchInput';

interface ChatInputProps {
  onSubmit: (text: string) => void;
  placeholder?: string;
  disabled?: boolean;
  conversationId?: string | null;
}

export function ChatInput({
  onSubmit,
  placeholder = 'Ask a follow-up...',
  disabled = false,
  conversationId = null,
}: ChatInputProps) {
  return (
    <SearchInput
      onSubmit={onSubmit}
      placeholder={placeholder}
      disabled={disabled}
      conversationId={conversationId}
      variant="chat"
    />
  );
}

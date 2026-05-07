import { SearchInput } from '@/components/home/SearchInput';

interface ChatInputProps {
  onSubmit: (text: string) => void;
  placeholder?: string;
  disabled?: boolean;
}

export function ChatInput({
  onSubmit,
  placeholder = 'Ask a follow-up...',
  disabled = false,
}: ChatInputProps) {
  return (
    <SearchInput
      onSubmit={onSubmit}
      placeholder={placeholder}
      disabled={disabled}
      variant="chat"
    />
  );
}

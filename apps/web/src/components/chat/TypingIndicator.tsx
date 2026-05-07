export function TypingIndicator() {
  return (
    <div className="flex items-center gap-2 py-4">
      <div className="flex gap-1">
        <span className="dot-1 size-1.5 rounded-full bg-muted-foreground" />
        <span className="dot-2 size-1.5 rounded-full bg-muted-foreground" />
        <span className="dot-3 size-1.5 rounded-full bg-muted-foreground" />
      </div>
      <span className="text-xs text-muted-foreground">Searching and analyzing...</span>
    </div>
  );
}

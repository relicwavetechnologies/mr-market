import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';

interface CitationBadgeProps {
  source: string;
  number: number;
  url?: string;
  title?: string;
}

export function CitationBadge({ source, number, url, title }: CitationBadgeProps) {
  const inner = (
    <span className="mx-0.5 inline-flex h-[18px] -translate-y-[1px] items-center gap-1 rounded-md border border-border/80 bg-accent/60 px-1.5 align-middle text-[10px] font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-foreground">
      <span className="font-mono text-[10px] text-foreground/70">{number}</span>
      <span className="truncate">{source}</span>
    </span>
  );

  if (url) {
    return (
      <Tooltip>
        <TooltipTrigger asChild>
          <a href={url} target="_blank" rel="noopener noreferrer" className="no-underline">
            {inner}
          </a>
        </TooltipTrigger>
        <TooltipContent side="top" className="max-w-xs">
          <div className="flex flex-col gap-0.5">
            {title && <span className="text-[12px] font-medium">{title}</span>}
            <span className="text-[11px] text-muted-foreground">{source}</span>
          </div>
        </TooltipContent>
      </Tooltip>
    );
  }
  return inner;
}

import type { Source } from "@/types";

interface SourceBadgeProps {
  index: number;
  source: Source;
}

export function SourceBadge({ index, source }: SourceBadgeProps) {
  const content = (
    <span
      className="inline-flex h-5 w-5 items-center justify-center rounded-full bg-accent/20 text-[10px] font-semibold text-accent transition-colors hover:bg-accent/30"
      title={source.title}
    >
      {index + 1}
    </span>
  );

  if (source.url) {
    return (
      <a
        href={source.url}
        target="_blank"
        rel="noopener noreferrer"
        className="inline-block"
      >
        {content}
      </a>
    );
  }

  return content;
}

import type { ReactNode } from 'react';
import type { Source } from '@/types';
import { CitationBadge } from '@/components/chat/CitationBadge';

/**
 * Parses inline content for [N] citation markers, **bold** text, and plain text.
 * Returns an array of React nodes.
 */
function parseInline(text: string, sources: Source[]): ReactNode[] {
  const nodes: ReactNode[] = [];
  // Match either **bold** or [N] citations
  const regex = /(\*\*[^*]+\*\*)|(\[(\d+)\])/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  let key = 0;

  while ((match = regex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      nodes.push(text.slice(lastIndex, match.index));
    }

    if (match[1]) {
      // Bold
      const inner = match[1].slice(2, -2);
      nodes.push(
        <strong key={`b-${key++}`} className="font-semibold text-foreground">
          {inner}
        </strong>
      );
    } else if (match[2]) {
      // Citation [N]
      const num = parseInt(match[3], 10);
      const source = sources[num - 1];
      if (source) {
        nodes.push(
          <CitationBadge
            key={`c-${key++}-${match.index}`}
            number={num}
            source={source.domain}
            url={source.url}
            title={source.title}
          />
        );
      } else {
        nodes.push(
          <CitationBadge
            key={`c-${key++}-${match.index}`}
            number={num}
            source="source"
          />
        );
      }
    }

    lastIndex = match.index + match[0].length;
  }

  if (lastIndex < text.length) {
    nodes.push(text.slice(lastIndex));
  }

  return nodes;
}

/**
 * Parses a markdown string into structured React elements (h2, ul, p)
 * with inline citation badges. Designed to render inside `.answer-copy`.
 */
export function parseMarkdown(content: string, sources: Source[] = []): ReactNode {
  if (!content) return null;

  const lines = content.split('\n');
  const blocks: ReactNode[] = [];
  let listBuffer: string[] = [];
  let paraBuffer: string[] = [];
  let blockKey = 0;

  const flushList = () => {
    if (listBuffer.length === 0) return;
    const items = listBuffer.map((line, idx) => (
      <li key={`li-${idx}`}>{parseInline(line, sources)}</li>
    ));
    blocks.push(<ul key={`ul-${blockKey++}`}>{items}</ul>);
    listBuffer = [];
  };

  const flushPara = () => {
    if (paraBuffer.length === 0) return;
    const text = paraBuffer.join(' ');
    blocks.push(
      <p key={`p-${blockKey++}`}>{parseInline(text, sources)}</p>
    );
    paraBuffer = [];
  };

  for (const rawLine of lines) {
    const line = rawLine.trim();

    // Empty line — flush both buffers
    if (line === '') {
      flushPara();
      flushList();
      continue;
    }

    // H2 heading
    if (line.startsWith('## ')) {
      flushPara();
      flushList();
      const headingText = line.slice(3);
      blocks.push(
        <h2 key={`h2-${blockKey++}`}>{parseInline(headingText, sources)}</h2>
      );
      continue;
    }

    // Bullet
    if (line.startsWith('- ') || line.startsWith('• ')) {
      flushPara();
      listBuffer.push(line.replace(/^[-•]\s+/, ''));
      continue;
    }

    // Regular paragraph line
    flushList();
    paraBuffer.push(line);
  }

  flushPara();
  flushList();

  return <>{blocks}</>;
}

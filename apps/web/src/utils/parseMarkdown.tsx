import type { ReactNode } from 'react';
import type { Source } from '@/types';
import { CitationBadge } from '@/components/chat/CitationBadge';

/**
 * Parses inline content. Recognises:
 *   - `**bold**`
 *   - `*italic*`  /  `_italic_`
 *   - `` `code` ``
 *   - `[N]` citation markers
 *
 * Order matters: bold (`**...**`) MUST be tested before italic (`*...*`)
 * because both share the asterisk character; alternation is left-to-right.
 */
function parseInline(text: string, sources: Source[]): ReactNode[] {
  const nodes: ReactNode[] = [];
  const regex =
    /(\*\*[^*]+\*\*)|(\*[^*\n]+\*)|(_[^_\n]+_)|(`[^`\n]+`)|(\[(\d+)\])/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  let key = 0;

  while ((match = regex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      nodes.push(text.slice(lastIndex, match.index));
    }

    if (match[1]) {
      // Bold
      nodes.push(
        <strong key={`b-${key++}`} className="font-semibold text-foreground">
          {match[1].slice(2, -2)}
        </strong>,
      );
    } else if (match[2]) {
      // *italic*
      nodes.push(<em key={`i-${key++}`}>{match[2].slice(1, -1)}</em>);
    } else if (match[3]) {
      // _italic_
      nodes.push(<em key={`u-${key++}`}>{match[3].slice(1, -1)}</em>);
    } else if (match[4]) {
      // `code`
      nodes.push(<code key={`c-${key++}`}>{match[4].slice(1, -1)}</code>);
    } else if (match[5]) {
      // Citation [N]
      const num = parseInt(match[6], 10);
      const source = sources[num - 1];
      nodes.push(
        <CitationBadge
          key={`cite-${key++}-${match.index}`}
          number={num}
          source={source ? (source.domain ?? source.title) : 'source'}
          url={source?.url}
          title={source?.title}
        />,
      );
    }

    lastIndex = match.index + match[0].length;
  }

  if (lastIndex < text.length) {
    nodes.push(text.slice(lastIndex));
  }

  return nodes;
}

const HEADING_RE = /^(#{1,6})\s+(.*)$/;

/**
 * Parses a markdown string into structured React elements (h1–h6, ul, ol, p)
 * with inline citation badges. Designed to render inside `.answer-copy`.
 */
export function parseMarkdown(content: string, sources: Source[] = []): ReactNode {
  if (!content) return null;

  const lines = content.split('\n');
  const blocks: ReactNode[] = [];
  let ulBuffer: string[] = [];
  let olBuffer: string[] = [];
  let paraBuffer: string[] = [];
  let blockKey = 0;

  const flushUl = () => {
    if (ulBuffer.length === 0) return;
    const items = ulBuffer.map((line, idx) => (
      <li key={`li-${idx}`}>{parseInline(line, sources)}</li>
    ));
    blocks.push(<ul key={`ul-${blockKey++}`}>{items}</ul>);
    ulBuffer = [];
  };

  const flushOl = () => {
    if (olBuffer.length === 0) return;
    const items = olBuffer.map((line, idx) => (
      <li key={`li-${idx}`}>{parseInline(line, sources)}</li>
    ));
    blocks.push(<ol key={`ol-${blockKey++}`}>{items}</ol>);
    olBuffer = [];
  };

  const flushPara = () => {
    if (paraBuffer.length === 0) return;
    const text = paraBuffer.join(' ');
    blocks.push(<p key={`p-${blockKey++}`}>{parseInline(text, sources)}</p>);
    paraBuffer = [];
  };

  const flushAll = () => {
    flushPara();
    flushUl();
    flushOl();
  };

  for (const rawLine of lines) {
    const line = rawLine.trim();

    if (line === '') {
      flushAll();
      continue;
    }

    // Heading: # → h1, ## → h2, ### → h3, etc.
    const headingMatch = line.match(HEADING_RE);
    if (headingMatch) {
      flushAll();
      const level = headingMatch[1].length;
      const headingText = headingMatch[2];
      const Tag = `h${Math.min(level, 6)}` as 'h1' | 'h2' | 'h3' | 'h4' | 'h5' | 'h6';
      blocks.push(
        <Tag key={`h-${blockKey++}`}>{parseInline(headingText, sources)}</Tag>,
      );
      continue;
    }

    // Unordered bullet
    if (line.startsWith('- ') || line.startsWith('* ') || line.startsWith('• ')) {
      flushPara();
      flushOl();
      ulBuffer.push(line.replace(/^[-*•]\s+/, ''));
      continue;
    }

    // Ordered list item: `1. foo`, `2) foo`, etc.
    const olMatch = line.match(/^(\d+)[.)]\s+(.*)$/);
    if (olMatch) {
      flushPara();
      flushUl();
      olBuffer.push(olMatch[2]);
      continue;
    }

    // Regular paragraph line
    flushUl();
    flushOl();
    paraBuffer.push(line);
  }

  flushAll();

  return <>{blocks}</>;
}
